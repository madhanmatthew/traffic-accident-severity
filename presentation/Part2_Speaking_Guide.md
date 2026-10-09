# Part 2 – Speaking Guide: Accident Severity MLOps Pipeline

Deck: `Part2_MLOps_Pipeline.pptx` · 16 slides · about 15–18 minutes.
The same script is in the PowerPoint speaker notes. Open **View → Notes**, or use Presenter View while presenting.

## 1. The project in plain words (read this first)

Part 1 produced a clean table: one row per collision, with only the facts known when it was reported. Part 2 trains a **machine-learning model** on that table to predict whether a collision is **Fatal, Serious or Slight**.

The "MLOps" part means I didn't stop at training. I built everything a real model needs to live in production:

1. **Track** every training run (MLflow), so results are reproducible and comparable.
2. **Version** the models in a registry, and only promote a new one to "champion" if it's genuinely better.
3. **Deploy** the champion as a web API (FastAPI) inside a Docker container, with a Streamlit front end.
4. **Monitor** what happens after deployment: is the incoming data changing (*drift*)? Is the model still catching severe crashes?
5. **Retrain** automatically when clear, written rules say so (a weekly Airflow job).

The hardest ML problem is **imbalance**: only 1.5% of crashes are fatal. A lazy model that always says "Slight" is 75.6% accurate and completely useless. So I used **class weights** and judged the model by **macro-F1** and **KSI recall** instead of accuracy.

## 2. Key terms you must be able to explain

| Term | What to say |
|---|---|
| MLOps | Engineering practices for running ML in production: tracking, versioning, deployment, monitoring and retraining. |
| Multi-class classification | Predicting one of several categories, here Fatal, Serious or Slight. |
| Class imbalance | Some classes are far rarer than others (Fatal 1.5%). Models tend to ignore rare classes. |
| Class weights (balanced) | Each training example is weighted inversely to its class frequency, so the model is penalised more for missing rare classes (Fatal ≈ 22 vs Slight ≈ 0.44). |
| LightGBM | A fast gradient-boosted decision tree library. It builds many small trees, each one correcting the errors of the previous ones. |
| Recall | Of all the real cases of a class, how many the model caught. |
| Precision | Of all the predictions of a class, how many were correct. |
| F1 / macro-F1 | F1 is the harmonic mean of precision and recall. Macro-F1 averages F1 over the classes equally, so rare classes count fully. |
| KSI recall / false-negative rate | Share of truly fatal or serious crashes predicted as fatal or serious (64.6%). FNR = 1 − recall (35.4%): the severe crashes the model missed. |
| Confusion matrix | A table of actual vs predicted classes. The diagonal shows the correct predictions. |
| Chronological split | Train on older data and test on newer data, so the model never sees the future. |
| sklearn Pipeline | A single object that chains feature engineering, preprocessing and the model, so training and serving run identical code. |
| Training–serving skew | A bug where production prepares inputs differently from training. One pipeline prevents it. |
| MLflow tracking | Logs the parameters, metrics, artefacts and model of every run. |
| Model registry / alias | Stores model versions. The `@champion` alias points to the version production uses. |
| Champion–challenger | A new model (challenger) replaces the champion only if it beats it on the same test data by at least 0.005 macro-F1. |
| FastAPI / REST endpoint | A Python web framework. `POST /predict` receives collision details as JSON and returns probabilities. |
| pydantic | Validates the input; a bad payload returns HTTP 422. |
| Docker / docker-compose | Packages the app with all its dependencies. Compose starts the API, the MLflow server and Streamlit together. |
| Data drift | The distribution of incoming data changes compared with the training data. |
| PSI | Population Stability Index: Σ (new% − ref%) × ln(new% / ref%) over the bins. Below 0.1 is stable, 0.1–0.2 is moderate, above 0.2 is a significant shift. |
| Retraining policy | Explicit rules in code (`RetrainingPolicy`) that decide when to retrain. |

## 3. Numbers to remember

- Split: train **Jan 2023–Jun 2024**, validation **Jul–Sep 2024**, test **Oct–Dec 2024**
- Test results: macro-F1 **0.431**, KSI recall **64.6%**, accuracy **62.1%** (always-"Slight" baseline: 75.6% accuracy, macro-F1 ≈ 0.29)
- Recall: Fatal **29.8%**, Serious **55.5%**, Slight **64.7%**. Fatal precision **≈ 9.4%**
- Confusion matrix: **324 of 389** fatal crashes (83%) predicted as fatal or serious; **3,248 of 5,851** serious caught; **6,325** slight crashes predicted as serious (false alarms)
- Promotion threshold: **+0.005** macro-F1 on the same test window
- Monitoring, labelled batch: **26,342** rows, no retraining. Simulated drift: **9,361** rows, **7** features drifted, police-force PSI **0.817**, centroid shift **43.7 km**, **RETRAIN**
- Retrain triggers: more than 3 features with PSI > 0.2 · class PSI > 0.1 · location PSI > 0.2 · macro-F1 drop > 0.05 · KSI FNR rise > 0.05 · model age > 180 days
- Warnings only: missing-rate rise > 10 points · API error rate > 2% · p95 latency > 300 ms

## Slide-by-slide script

### Introduction

**Slide 1 – Title slide**

> Good morning. I am Madhan Matthew S, USN 1CR23AI052, from 7A AIML. In Part 2, I take the clean table from Part 1 and build a complete MLOps system around a machine-learning model.
>
> MLOps means applying engineering discipline to machine learning. It's not only about training a model once in a notebook. It means tracking every experiment, versioning models, deploying the model as a real service, monitoring it in production, and having clear rules for when to retrain it.
>
> The model predicts whether a collision is Fatal, Serious or Slight, using only information available when the collision is reported.

**Slide 2 – Goal: predict severity when a crash is reported**

> The goal is simple to state. When a collision is reported, can we predict how severe it will turn out to be?
>
> The input is the ml_accident_features table from Part 1: 205,173 collisions. The model uses 35 features, including time, location, road type, speed limit, light conditions, measured weather, and which vehicles were involved.
>
> The output is a probability for each of the three classes: Fatal, Serious and Slight.
>
> Why is this useful? A system like this could flag the collisions that are likely to be serious or fatal, so emergency and road-safety resources can be prioritised.
>
> I want to stress one thing. Every feature is something known at the time of reporting. The model never sees anything that is only known after the outcome.

**Slide 3 – The core difficulty: severe crashes are rare**

> The biggest difficulty is class imbalance, which I showed at the end of Part 1.
>
> 75.6 percent of collisions are slight and only 1.5 percent are fatal.
>
> Here's why that matters. Imagine a lazy model that always answers "Slight". It would be 75.6 percent accurate, which sounds good, but it would miss every single fatal and serious collision. Those are exactly the ones we care about.
>
> So accuracy is the wrong metric for this problem. Instead, I focus on two metrics.
>
> Macro-F1: the F1 score is calculated for each class separately and then averaged, so the rare Fatal class counts as much as the common Slight class.
>
> KSI recall: out of all the collisions that really were fatal or serious, what percentage did the model catch? Missing a severe collision, a false negative, is the costly mistake in road safety.

### Model development

**Slide 4 – End-to-end MLOps architecture**

> This is the whole system on one slide. It's a loop, not a straight line.
>
> Top row, from left to right. The features come from Part 1. The training script builds the model pipeline. Every training run is logged to MLflow. Then the model is registered in the MLflow Model Registry, and the best model gets the "champion" label.
>
> Then down to the bottom row. The champion model is served by a FastAPI web service running in a Docker container. A Streamlit app lets users enter a collision and get a prediction. Every prediction is written to a log.
>
> The monitoring script reads new data and the prediction log, checks for drift and performance drops, and decides whether to retrain. If yes, we go back to training, and the loop closes.
>
> An Airflow DAG runs this monitor-and-retrain cycle every Monday.

**Slide 5 – Chronological split: no peeking into the future**

> An important design decision was how to split the data into training and test sets.
>
> Most tutorials use a random split. But for time-based data, that's a mistake. With a random split, the model trains on collisions from December 2024 and is then tested on collisions from January 2023. It learns future seasonal patterns that it could never know in real life, and the test score becomes too optimistic.
>
> So I split by time. I train on January 2023 to June 2024, which is 18 months. I use July to September 2024 for validation, and October to December 2024 as the final test.
>
> This copies how the model is really used: it learns from the past and predicts the future. All the results I'm about to show are on the test period, which the model never saw during training.

**Slide 6 – One pipeline from raw features to prediction**

> Here is how the model itself is built. It's a single scikit-learn Pipeline object with three stages.
>
> Stage one is my own custom transformer, the AccidentFeatureEngineer. It creates new features. Cyclical time: hour 23 and hour 0 are next to each other, so I encode the hour and month with sine and cosine. It also creates flags like "is it dark", "is the road wet", "is it a high-speed road", and "is a vulnerable road user involved", meaning a pedestrian, cyclist or motorcyclist.
>
> Stage two is a ColumnTransformer. It fills missing numbers with the median and one-hot encodes the categories. Rare categories are grouped into an "infrequent" bucket, so an unseen category in production doesn't crash the model.
>
> Stage three is the LightGBM classifier. LightGBM is a gradient-boosted decision tree library. It's fast on 200,000 rows and handles mixed data well.
>
> Why put everything in one pipeline? Because the exact same code runs in training and in serving. There's no risk of the API preparing the data differently from training, which is a common bug called training-serving skew.

**Slide 7 – Tackling imbalance with class weights**

> So how did I handle the imbalance? I used balanced class weights.
>
> The idea is simple. During training, each collision gets a weight that is inversely proportional to how common its class is. Slight collisions are very common, so each one gets a small weight, about 0.44. Serious ones get about 1.5. Fatal collisions are rare, so each one gets a weight of about 22.
>
> In other words, getting one fatal collision wrong hurts the model about 50 times more than getting one slight collision wrong. This forces the model to pay attention to the rare, severe cases.
>
> The trade-off is that the model will now predict "Serious" or "Fatal" more often, including some false alarms. Overall accuracy goes down, but recall on the severe classes goes up. For road safety, that's the right trade: a false alarm costs a little, but a missed fatal collision costs a lot.
>
> I chose weighting over oversampling methods like SMOTE because weighting doesn't create any synthetic collisions. The model trains only on real data.

### Results

**Slide 8 – Results on the unseen test period (Oct–Dec 2024)**

> Here are the results on the test period, October to December 2024, which the model never saw.
>
> The most important number is KSI recall: 64.6 percent. Out of all the collisions that really were fatal or serious, the model flagged about two out of three as severe.
>
> Macro-F1 is 0.431. That sounds low, but for a three-class problem with a 1.5 percent class and no information about speed at impact, it's reasonable. A model that always says "Slight" would get a macro-F1 of only about 0.29.
>
> Per class, the chart shows recall: Fatal 29.8 percent, Serious 55.5 percent and Slight 64.7 percent.
>
> Accuracy is 62.1 percent, which is lower than the 75.6 percent of the lazy "always Slight" model. That's intentional: it's the price of catching severe collisions, as I explained on the previous slide.

**Slide 9 – Confusion matrix: where the model is right and wrong**

> This is the confusion matrix for the test period. The rows are what really happened, and the columns are what the model predicted. The highlighted diagonal shows the correct predictions.
>
> Look at the Fatal row. There were 389 fatal collisions. The model predicted 116 as fatal and another 208 as serious. So 324 of the 389 fatal collisions, 83 percent, were flagged as severe in some way. Only 65 were predicted as slight. That's an encouraging result.
>
> For Serious, 3,248 out of 5,851 were caught.
>
> The main weakness is the bottom row. 6,325 slight collisions were predicted as serious. Those are false alarms. That's the cost of the class weighting, and it's also why Fatal precision is low, at about 9 percent. In future work I would tune the decision thresholds to balance this more carefully.

### Tracking, deployment and monitoring

**Slide 10 – MLflow: every run tracked, every model versioned**

> MLflow is the tool I used to track experiments and manage model versions.
>
> Every training run logs four things. The parameters: split dates, LightGBM settings and the weighting. The metrics: macro-F1, per-class recall, precision and F1, and the KSI false-negative rate. The artefacts: confusion matrices, classification reports and the training data profile. And the model itself, with its input signature.
>
> Then comes the registry and the champion-challenger gate. Every run registers a new version of "traffic-severity-classifier". But the "champion" alias, the version that production uses, only moves if the new model beats the current champion's macro-F1 by at least 0.005 on the same test window. Otherwise the old champion stays. So a worse model can never replace a better one by accident.
>
> Rollback is easy: you just move the alias back to the old version. Versions are never deleted, so every prediction can be traced back to the model version that made it.

**Slide 11 – Serving the model: FastAPI in Docker**

> To deploy the model, I built a REST API with FastAPI.
>
> There are five endpoints. POST /predict for a single collision. POST /predict/batch for many at once. GET /health to check the service is alive. GET /model-info, which shows which model version is running and its metrics. And GET /metrics, which reports latency and error rate.
>
> Inputs are validated with pydantic. If someone sends an invalid payload, for example a text value where a number is expected, the API returns a 422 error and counts it as a failure. Every request is logged with its model version, which feeds the monitoring.
>
> Everything is containerised. The Dockerfile bakes the champion model into the image, and docker-compose starts three services: the API on port 8000, the MLflow server on 5000, and the Streamlit UI on 8502. The Streamlit app has a prediction form that calls the API, a model card, and a monitoring view.
>
> [If possible, demo here: open localhost:8000/docs and run a prediction, or use the Streamlit form.]

**Slide 12 – Monitoring: six signals watched every week**

> Once a model is deployed, the world keeps changing. Road layouts change, weather changes with the seasons, and policing practices change. So the model's performance can quietly get worse over time. This is called drift. My monitoring script watches six signals.
>
> One, input data quality: are more values suddenly missing, or are there unseen categories?
>
> Two, feature drift, measured with PSI, the Population Stability Index. PSI compares the distribution of a feature in new data with its distribution in the training data. Below 0.1 means stable, 0.1 to 0.2 is a moderate shift, and above 0.2 is a significant shift.
>
> Three, class drift: is the mix of predicted classes, or of actual classes, changing?
>
> Four, location drift: are collisions coming from different police forces than before? I also measure how far the geographic centre of the collisions has moved, in kilometres.
>
> Five, performance: macro-F1 and the KSI false-negative rate, whenever labels are available.
>
> Six, latency and failures from the API.

**Slide 13 – Monitoring in action: two real runs**

> Here are two real monitoring runs that show the system working.
>
> On the left is the normal case. I ran the monitor on the labelled batch from October to December 2024: 26,342 collisions. The decision was no retraining needed. Macro-F1 was stable at 0.431, and the predicted class mix matched the reference almost exactly. There were two warnings: some temperature drift, which is expected because it's winter data, and a small missing-value increase in one column. Warnings are reported, but they don't trigger retraining.
>
> On the right, I deliberately simulated drift. I built a batch shifted towards rural, night-time, wet-road collisions, to check that the alarms actually fire. They did. Seven key features drifted with a PSI above 0.2, the police-force location PSI was 0.817, and the centre of the collisions moved by 43.7 kilometres. The predicted fatal share jumped from 4.7 percent to 13.2 percent. Decision: RETRAIN.
>
> So the monitor stays quiet when nothing has changed, and it raises the alarm when the data really shifts. That's exactly what you want.

**Slide 14 – Retraining policy and model lifecycle**

> The retraining decision isn't a feeling. It's an explicit policy written in code, in the RetrainingPolicy class.
>
> Retraining is triggered if any one of six conditions holds. More than three key features have PSI above 0.2. The class distribution PSI is above 0.1. The location PSI is above 0.2. Macro-F1 has dropped by more than 0.05. The KSI false-negative rate has risen by more than 0.05. Or the champion is older than 180 days, which is a scheduled refresh.
>
> On the right are three conditions that only raise warnings: a big jump in missing values, an API error rate above 2 percent, or p95 latency above 300 milliseconds. Why don't these trigger retraining? Because they point to a broken upstream feed or an infrastructure fault. If you retrain on broken data, you just make the model worse. The right fix is to repair the pipeline first.
>
> All of this runs automatically. An Airflow DAG runs every Monday: monitor, then branch, then either retrain or skip. Retraining goes through the same champion-challenger gate, so the lifecycle is fully closed.

### Wrap-up

**Slide 15 – Limitations and future work**

> Some honest limitations.
>
> Weather is at the one-degree grid, so it describes regional rather than street-level conditions.
>
> Severity depends heavily on things that simply aren't recorded at report time, like the speed at impact or whether seatbelts were worn. That puts a ceiling on how well any model can perform with this data.
>
> The probabilities aren't calibrated, so a predicted 30 percent doesn't necessarily mean a 30 percent chance. And Fatal precision is low, around 9 percent, so there are many false alarms.
>
> For future work: calibrate the probabilities, tune the decision thresholds to hit a target KSI recall, add richer road context from OpenStreetMap, compare LightGBM against other models like XGBoost in a tracked experiment, and use canary deployments, sending a small share of traffic to a new model first.

**Slide 16 – Summary: a model with a full lifecycle**

> To summarise Part 2.
>
> I built a severity classifier: a single LightGBM pipeline with class weighting and a chronological split. On unseen data it catches about 65 percent of severe collisions, and 83 percent of fatal ones are flagged as severe.
>
> I made it operational: every run is tracked in MLflow, models are versioned with a champion-challenger gate, and the champion is served by FastAPI in Docker with a Streamlit front end.
>
> And I kept it healthy: monitoring for data quality, drift, location shift, recall and latency, plus an explicit retraining policy that runs weekly in Airflow.
>
> Together with Part 1, the whole project goes from raw public data all the way to a monitored, self-maintaining prediction service.
>
> Thank you. I'm happy to take questions.

## Questions faculty may ask – and how to answer

**Why is accuracy (62%) lower than just predicting "Slight" (75.6%)? Isn't that worse?**
It's deliberate. Predicting "Slight" every time misses every fatal and serious crash. Class weighting trades some accuracy for catching severe collisions (KSI recall 64.6%), because in road safety a missed severe crash costs far more than a false alarm.

**A macro-F1 of 0.43 seems low. Is the model bad?**
For three classes with a 1.5% minority, it's reasonable. The always-"Slight" baseline has a macro-F1 of about 0.29. Severity also depends on things not recorded at report time, like speed at impact and seatbelt use, which puts a ceiling on any model built from this data.

**Why class weights and not SMOTE or oversampling?**
Weighting uses only real collisions and adds no synthetic rows. It's built into LightGBM and keeps the pipeline simple and reproducible.

**Why LightGBM?**
It's fast on about 200k rows, handles mixed numeric and categorical features and missing values well, and supports sample weights. *(Be honest if asked: the final pipeline trains LightGBM only. Comparing it against XGBoost or random forest in tracked MLflow runs is future work.)*

**Why a chronological split instead of random?**
A random split puts future months in the training data, so the model learns seasonal patterns it couldn't know in real use, and the test score is too optimistic. A chronological split copies real deployment.

**How does a model become "champion"?**
Every run registers a new version. The `@champion` alias only moves if the new model's test macro-F1 beats the current champion's by at least 0.005 on the same test window. The threshold stops us promoting random noise.

**How do you roll back?**
Move the alias back to the previous version (`set_registered_model_alias`) and restart or re-export. Versions are never deleted.

**What is PSI, and why 0.2?**
PSI measures how much a distribution has shifted between the reference (training) data and new data. 0.1 and 0.2 are the standard industry rules of thumb for moderate and significant shift.

**Why don't data-quality, latency or error-rate problems trigger retraining?**
They usually mean a broken upstream feed or an infrastructure fault. Retraining on broken data makes the model worse, so they raise warnings to fix the cause first.

**How did you prove the monitoring works?**
Two runs. A normal labelled batch (Oct–Dec 2024) correctly gave "no retraining needed". A deliberately shifted batch (rural, night, wet) correctly gave "RETRAIN": 7 features drifted, location PSI 0.817.

**How would you improve fatal precision (9%)?**
Tune the decision thresholds for a target KSI recall, calibrate the probabilities, and add richer features such as road context from OpenStreetMap.

**How is the API tested?**
pytest uses FastAPI's test client to check `/predict`, `/predict/batch`, validation errors (422), `/metrics` and the prediction log. Other tests cover feature engineering, the chronological split, class weights, metric definitions and PSI.

**Could this be used in real life? Any ethical concerns?**
It's a decision-support tool, not a replacement for human judgement. False negatives matter most, so we monitor the KSI false-negative rate. The data is open and has no personal information. Any real use would need calibration and validation with domain experts.
