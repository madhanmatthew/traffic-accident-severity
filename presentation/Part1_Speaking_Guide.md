# Part 1 – Speaking Guide: Traffic Accident Data Pipeline

Deck: `Part1_Data_Pipeline.pptx` · 16 slides · about 15–18 minutes.
The same script is in the PowerPoint speaker notes. Open **View → Notes**, or use Presenter View while presenting.

## 1. The project in plain words (read this first)

Every year about 100,000 road collisions with injuries happen in Great Britain. The police record each one in a national dataset called **STATS19**. About 1 in 4 of them is **KSI**, meaning someone was Killed or Seriously Injured.

The project asks: **when, where and under what conditions do collisions become severe, and can we predict it?**

- **Part 1 (this deck)** is the *data engineering* half. I built an automated "factory line" for data. It downloads the raw police files and real hourly weather, checks the data for errors, joins everything together, and stores it in a well-organised database (a *warehouse*). A dashboard then shows the patterns, and the pipeline produces a clean table for machine learning.
- **Part 2** is the *machine learning and MLOps* half. It trains a model on that table, deploys it as a web service, and monitors it.

A simple analogy for Part 1: raw ingredients (CSV files and weather) arrive at a kitchen. They're stored untouched (**raw**), washed and labelled (**staging**), inspected, with bad ones thrown out and noted down (**cleaned**), and cooked into dishes (**analytics**). Then they're served on organised shelves (**warehouse**) to customers (**dashboard** and **ML model**). **Airflow** is the head chef who runs every step on schedule, every month.

## 2. Key terms you must be able to explain

| Term | What to say |
|---|---|
| STATS19 | The UK Department for Transport's official dataset of police-reported injury road collisions. It has 3 linked tables: collision, vehicle and casualty. |
| KSI | Killed or Seriously Injured: a collision whose severity is Fatal or Serious. It's the main UK road-safety measure. |
| Open-Meteo | A free historical weather API. I used hourly temperature, rain, snow, wind, cloud and humidity. |
| Grid cell | I divided Great Britain into 1°×1° squares (59 cells). Each collision takes the weather of its square for that hour. |
| HTTP 429 | "Too Many Requests": the API's rate limit. I solved it with a coarser grid and request pacing. |
| ETL | Extract, Transform, Load: take data from sources, clean and reshape it, and load it into a database. |
| Apache Airflow / DAG | A workflow scheduler. A DAG (Directed Acyclic Graph) is the list of tasks and their order. Mine has 10 tasks and runs monthly. |
| Idempotent | Running a task again gives the same result and doesn't duplicate or break anything. So any failed task can be safely re-run. |
| Parquet | A compressed, column-based file format. It's fast to read and keeps data types. I used it for every intermediate layer. |
| Raw / staging / cleaned / analytics | The data layers. Raw is the untouched copy. Staging fixes names and types. Cleaned applies the validation rules. Analytics holds the joined features and tables. |
| Validation rule (REJECT / NULLIFY) | A data-quality check. REJECT drops the row. NULLIFY keeps the row but blanks the bad value. |
| Quality gate | If more than 5% of collisions are rejected, the run fails. That protects the warehouse from a broken source file. |
| Star schema | A warehouse design. A central *fact* table holds the events (1 row per collision), and *dimension* tables describe the context (date, time, location, road, weather, severity). |
| Data mart | Pre-aggregated summary tables (by hour, by road, by condition, hotspots) that keep the dashboard fast. |
| PostGIS | An extension that adds geographic data types and spatial indexes to PostgreSQL, used for hotspot and radius queries. |
| Target leakage | When a model's input contains information only known *after* the outcome. The model then looks great in testing but fails in reality. I removed casualty severity counts and police attendance to prevent it. |
| Streamlit | A Python library for building interactive web dashboards. |

## 3. Numbers to remember

- 2023–2024 data: **205,185** collisions, **373,329** vehicles, **261,249** casualties (**839,763** rows from 6 files)
- Weather: **59** grid cells, **117** API responses, **1,026,312** hourly rows, **0** failures, **430 s**, **100%** match
- Validation: **22** rules. **46** records rejected (12 collisions without coordinates + 34 orphans), **0.006%** reject rate
- Warehouse: **16** tables reconciled, **1,061,721** rows loaded in **51 s**. ML table: **205,173 × 44**
- Severity: Slight **75.6%**, Serious **22.9%**, Fatal **1.5%**, KSI **24.4%**
- KSI rate: dark with no street lights **34.5%** vs daylight **23.3%**; 60 mph **34.3%** vs 20 mph **19.7%**; rural **29.4%** vs urban **21.9%**
- Tests: **12** pytest tests passing

## Slide-by-slide script

### Introduction

**Slide 1 – Title slide**

> Good morning. I am Madhan Matthew S, USN 1CR23AI052, from 7A AIML. My project is Project 4: Traffic Accident Severity Analytics and Prediction. It has two parts. Today, in Part 1, I'll explain the data pipeline.
>
> In one sentence: I built an automated pipeline that downloads every police-reported road collision in Great Britain for 2023 and 2024, adds the real measured weather at the time of each crash, checks and cleans the data, stores it in a proper data warehouse, and shows the patterns on a dashboard.
>
> The cleaned output of this part is also the input for Part 2, where I train a machine-learning model to predict how severe a collision is.

**Slide 2 – Why this problem matters**

> First, why does this matter?
>
> Great Britain records around 100,000 road collisions with injuries every year. About one in four of them kills or seriously injures someone. We call that KSI: Killed or Seriously Injured. That is the main road-safety measure the UK government uses.
>
> Road-safety teams want to know when, where and under which conditions a collision becomes severe, so they can decide where to put speed cameras, street lighting, or gritting in winter.
>
> The problem is the data. The police records describe the weather only as the officer saw it, like "raining" or "fine". They don't have measured values like temperature or millimetres of rain. And the data is spread across three separate files: collisions, vehicles and casualties.
>
> So my job was to bring all of this together into one reliable, automated system. I covered 205,185 collisions over two years.

**Slide 3 – What I set out to build**

> These were my five objectives.
>
> One: Ingest. Download the public collision data and enrich every collision with hourly weather.
>
> Two: Validate. Check the data with clear rules and keep a record of every row I reject, and why.
>
> Three: Store. Put the data into a warehouse that understands both time and location, so we can ask "where" and "when" questions quickly.
>
> Four: Visualise. Build a dashboard so anyone can explore the patterns.
>
> Five: Prepare for machine learning. Produce a clean, model-ready table for Part 2. The important word here is "leakage-free". I'll explain that later.
>
> And the whole thing had to be automated and repeatable, not a one-off notebook.

### Data and architecture

**Slide 4 – Two open data sources**

> I used two open data sources.
>
> The first is STATS19. This is the official road-safety dataset from the UK Department for Transport. Every injury collision the police record goes into it. It comes as three CSV files per year: collisions, vehicles and casualties. They are linked by a collision ID. For two years that's six files and about 840,000 rows.
>
> The second is Open-Meteo. It's a free historical weather API, and it doesn't need an API key. For every location and hour it gives the temperature, precipitation, rain, snowfall, wind speed and gusts, cloud cover and humidity. I downloaded just over one million hourly weather rows.
>
> Both are open licences, and there is no personal data. Any database passwords come only from environment variables. They are never written in the code.

**Slide 5 – Architecture: data moves through layers**

> This is the architecture. The data moves through layers from left to right, and each layer has one job.
>
> Raw: an exact copy of what I downloaded. I never change it, so I can always go back to the original.
>
> Staging: here I harmonise column names and fix data types. One real issue: in the 2024 files the Department for Transport renamed the columns from "accident" to "collision". Staging maps both versions to the same names, so the rest of the pipeline doesn't break.
>
> Cleaned: this is where the 22 validation rules run.
>
> Analytics: here I add the weather, create the features, and build the star schema tables.
>
> Warehouse: PostgreSQL with the PostGIS extension for location queries.
>
> Then the dashboard and the machine-learning table for Part 2 read from the warehouse.
>
> Each layer is saved as Parquet files in its own folder per run, so I can open and inspect every intermediate step.

**Slide 6 – Airflow runs ten idempotent tasks**

> Apache Airflow automates the pipeline. It's a workflow scheduler: you define the tasks and the order they run in, and Airflow runs them on a schedule, retries failures and shows logs.
>
> My DAG has ten tasks, from extract STATS19 through to publish run log. It runs automatically at 2 a.m. on the first of every month.
>
> The key design idea is idempotency. That means you can run a task again and get the same result without breaking anything. Every task gets the same run ID, and the tasks pass data through run-specific folders instead of through Airflow's memory. So if one task fails, I can re-run just that task.
>
> Retries: each task retries twice. The weather task retries three times, with 30-minute gaps, because of API limits.
>
> And the last task, publish run log, runs even if something earlier failed. That way failed runs are also recorded in the warehouse.

### How I solved the hard parts

**Slide 7 – Challenge: the weather API kept blocking me**

> This was the biggest technical challenge in Part 1.
>
> To match weather to each collision, I divided Great Britain into a grid. Every collision is "snapped" to its grid cell, and I download hourly weather for each cell.
>
> My first design used a fine half-degree grid: 192 cells. But Open-Meteo's free tier charges each request by the number of locations times the number of days. That design would have cost about 10,000 weighted calls. The API started returning HTTP 429, which means "Too Many Requests". My retry logic handled it, but it would have taken far too long.
>
> So I changed the design. First, a one-degree grid: 59 cells, which is about 3,000 calls. Second, the code calculates the weight of every request in advance and sleeps just enough to stay under 500 calls per minute. Third, after any 429 it waits at least 65 seconds.
>
> I also designed a safe failure path. If a weather request still fails, it's logged as FAILED and the pipeline continues. Those collisions still keep the police-recorded weather. So a weather problem degrades the enrichment, but it never stops the warehouse refresh.
>
> Result: 117 weather responses, over one million hourly rows, zero failures, in about seven minutes. Every single collision was matched to weather.

**Slide 8 – 22 validation rules guard the warehouse**

> Next, data quality. I wrote 22 validation rules. They check things like missing IDs, duplicates, invalid dates and times, a severity that isn't 1, 2 or 3, missing coordinates or coordinates outside the UK, impossible speed limits, orphaned vehicle or casualty records, unrealistic ages, and impossible weather values.
>
> Every rule takes one of two actions. REJECT removes the whole row, for example a collision with no location. NULLIFY keeps the row but blanks one bad value, for example a driver age of 150.
>
> Every rule hit is written to a rejected-records file and a database table: which record, which rule, which field, what value, and from which file. So nothing disappears silently.
>
> There's also a quality gate. If more than 5 percent of collisions are rejected, the whole run fails. That stops a broken source file from ever reaching the warehouse.
>
> On the real data, only 46 records were rejected: 12 collisions with no coordinates, plus the 34 vehicles and casualties attached to them. That's 0.006 percent. The government data is well curated, so here the rules are mainly safeguards for future monthly refreshes.

**Slide 9 – Transformation: enriching every collision**

> After cleaning, the transform step makes the data useful.
>
> Standardise: I build a proper date-time and derive the hour, weekday, month, season and time band. The data stores categories as numeric codes. For example, light conditions code 6 means "darkness, no lighting". I map more than 20 coded fields to readable labels. If an unknown code ever appears, it becomes "Unknown (code N)" instead of crashing the pipeline.
>
> Weather join: each collision is joined to its grid cell's weather for that hour. I enforced a many-to-one check, so one weather hour can never duplicate a collision. The match rate was 100 percent.
>
> Vehicle and casualty features: for each collision I calculate things like whether a motorcycle, bicycle, bus or goods vehicle was involved, whether a pedestrian was hurt, and the youngest driver's age.
>
> Finally, the ML-ready table: 205,173 rows and 44 columns. The key point is that it only contains information that is known at the moment a collision is reported. I deliberately removed casualty severity counts and police attendance, because those are only known after the outcome. If they were left in, the model would effectively be seeing the answer. That's called target leakage, and it makes a model look great in testing but useless in real life.

**Slide 10 – Star schema warehouse in PostgreSQL + PostGIS**

> For storage I used a star schema. It's the standard design for analytical warehouses.
>
> In the middle is the fact table, fact_accident: one row per collision with the measurements. Around it are dimension tables that describe the context: date, time of day, location, road, weather and severity. With this design, a question like "KSI rate on rural roads at night in the rain" is just a simple join. There are also fact tables for vehicles and casualties.
>
> On top of that I built an accident mart. These are pre-aggregated tables by hour, by day, by road type, by condition, and a hotspot grid. They make the dashboard fast.
>
> PostGIS adds real geographic point columns with a spatial index, so the warehouse can do radius and hotspot queries.
>
> After loading, a verify step reconciles the row counts of all 16 tables against the Parquet files and checks the foreign keys. The run loaded over a million rows in 51 seconds.
>
> All the tables come from one SQLAlchemy schema definition. That same definition also generates the SQL DDL and the data dictionary, so the documentation can never drift away from the real database.

### Results

**Slide 11 – Interactive Streamlit dashboard**

> To make the data useful for people, I built a Streamlit dashboard that queries the star schema.
>
> On the left are filters for year, nation, urban or rural, police force and severity. At the top are six KPIs: total collisions, fatal, serious, the KSI rate, casualties and the weather match rate.
>
> It has six tabs. Severity distribution and monthly trend. Time patterns, including an hour-by-weekday heat map. Weather and road conditions, where you pick a factor and see its volume and KSI rate. A hotspot map. Vehicles and casualties. And a pipeline and data-quality tab that shows the run logs and the rejected records, so the audit trail is visible to users too.
>
> [If possible, switch to the live dashboard here and show the hotspot map and the conditions tab.]

**Slide 12 – Severity is highly imbalanced**

> Now the findings, starting with the most important one.
>
> Severity is very imbalanced. 75.6 percent of collisions are slight, 22.9 percent serious and only 1.5 percent fatal. So about one in four collisions is KSI.
>
> This matters a lot for Part 2. A machine-learning model trained on this data can just predict "slight" every time and still look about 76 percent accurate. Handling this imbalance is the main modelling challenge, and I'll show how I dealt with it in Part 2.
>
> On volume: collisions peak in the weekday evening rush hour, from 3 to 6 p.m. Friday is the busiest day with 33,600 collisions, and Sunday is the quietest with 23,100.

**Slide 13 – Frequent is not the same as severe**

> This is my favourite finding. The chart shows the KSI rate, meaning the share of collisions that are fatal or serious, under different conditions.
>
> The red bars are the most dangerous conditions. Darkness with no street lighting: 34.5 percent KSI, compared with 23.3 percent in daylight. 60 mph roads: 34.3 percent, compared with 19.7 percent on 20 mph roads. Night-time between midnight and 5 a.m.: 30.5 percent. Rural roads: 29.4 percent, against 21.9 percent urban.
>
> An interesting one is rain. Heavy rain increases the number of collisions, but the KSI rate actually drops slightly, 22.5 versus 24.6 when it's dry. This makes sense, because people drive slower in bad weather.
>
> Also, 31 percent of pedestrian casualties are KSI, compared with 20 percent of drivers and riders. And the five busiest 5 km hotspot cells are all in central London.
>
> So the conclusion for road safety is that the conditions that make crashes frequent, urban rush hour, are different from the ones that make them severe: unlit, rural, high-speed roads at night. They need different interventions. This also motivates Part 2: predicting severity is a different problem from predicting volume.

### Wrap-up

**Slide 14 – Built to be reliable and reproducible**

> This slide covers the engineering practices that make the pipeline trustworthy.
>
> Full audit trail: every download, step and rejection is logged both as CSV and in database tables.
>
> Quality gate: bad data stops the run instead of reaching users.
>
> Load verification: row counts and foreign keys are checked after every load.
>
> Safe re-runs: tasks are idempotent, and the annual raw files are cached, so a monthly refresh doesn't download everything again.
>
> Single source of truth: the schema is defined once in code, and the DDL and data dictionary are generated from it.
>
> Tested and containerised: 12 pytest tests cover the rules, joins, banding, keys and calendar. Docker Compose starts PostGIS, Airflow and the dashboard with one command. And no credentials are ever stored in the code.

**Slide 15 – Limitations and future work**

> I also want to be honest about the limitations.
>
> First, the one-degree weather grid gives regional weather, not street-level weather. A finer grid is supported in the code, but it needs about three times more API quota, or a paid tier.
>
> Second, STATS19 only includes injury collisions that the police recorded, and some severity misclassification is known.
>
> Third, I don't have traffic-volume data. So my rates are "the share of collisions that are severe", not "risk per vehicle-kilometre".
>
> For future work: add OpenStreetMap road context like lighting and number of lanes, switch to incremental loads instead of a full refresh, and add formal data contracts with a tool like Great Expectations.

**Slide 16 – Summary: from raw files to road-safety insight**

> To summarise Part 1.
>
> What I built: an automated monthly Airflow pipeline that takes two open data sources, about 1.9 million input rows, through raw, staging, cleaned and analytics layers into a PostGIS star schema and a dashboard.
>
> What I solved: API rate limits, by redesigning the weather grid and pacing requests. Schema changes between years, by harmonising in staging. And data quality, with 22 rules, a quality gate and a full audit trail.
>
> What I delivered: clear road-safety insights, and a leakage-free, model-ready table that is the starting point for Part 2.
>
> Thank you. I'm happy to take questions.

## Questions faculty may ask – and how to answer

**Why Airflow and not a simple cron job or a script?**
Airflow gives dependencies between tasks, retries, logs per task, a UI to see which step failed, and the ability to re-run one task. Cron would just run a script. I also kept a CLI (`traffic-pipeline run`), so the same steps work without Airflow.

**Why store Parquet files *and* a database?**
The Parquet layers make every intermediate state inspectable and reproducible: I can open the staging or cleaned data for any run. The database holds only the final analytical and audit tables that the dashboard and model use.

**Isn't a 1° weather grid too coarse?**
Yes, it gives regional, not street-level, weather. I listed this as a limitation. It was a deliberate trade-off against the free API quota (0.5° would need about 3× the calls). The code supports a finer grid, and the police-recorded weather is still available as a feature.

**How do you make sure the weather hour matches the collision hour?**
I requested weather in Europe/London local time, which is the same timezone as the STATS19 times. I floor the collision time to the hour and join on (cell, hour) with `validate="many_to_one"`, so one collision can never be duplicated.

**What happens if a download fails?**
STATS19 is mandatory, so the task fails and Airflow retries it twice. Weather is optional: a failed request is logged as FAILED, the run continues, and those collisions keep `weather_matched = false` with the police-recorded weather.

**Only 46 rows were rejected. Are the rules useful?**
The government data is well curated, so few rows fail today. The rules are safeguards for future monthly refreshes, for example if a file arrives broken or a format changes. The quality gate stops bad data from reaching the warehouse.

**What is idempotency and why does it matter?**
Re-running a task gives the same result. Each task writes to a run-specific folder and the warehouse is fully rebuilt, so retries never create duplicates.

**Why a star schema?**
It makes analytical questions simple and fast: one fact table joined to small dimension tables. For example, "KSI rate on rural roads at night in the rain" is just a filter on dimensions.

**How did you prevent target leakage?**
The ML table contains only information known when a collision is reported. Casualty severity counts and police attendance were removed, because they reveal or depend on the outcome.

**Why full refresh instead of incremental loading?**
Two years of data rebuilds in under a minute, and a full refresh guarantees the warehouse always matches exactly one pipeline run. Incremental loading is listed as future work for larger volumes.

**How is it reproducible?**
Everything is code: the pipeline, the schema (which generates the DDL and data dictionary), Docker Compose for PostGIS, Airflow and the dashboard, and configuration through environment variables. Each run's logs and evidence are saved in `docs/execution_evidence/`.
