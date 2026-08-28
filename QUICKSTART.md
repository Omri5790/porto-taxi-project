# כשאתה חוזר — שתי פקודות

## 1. להביא את הדאטהסט ל-GCS

**אם `train.csv` כבר אצלך על המק:**
```bash
gcloud storage cp train.csv gs://porto-taxi-project-bf990986/raw/train.csv
```

**אם לא — הרץ ב-Cloud Shell** (מוריד, פותח שני zipים, מעלה):
```bash
bash tools/fetch_dataset.sh
```

## 2. להריץ את כל הפייפליין

```bash
bash scripts/run_pipeline_dataproc.sh
```

מקים קלאסטר אחד עם **1 master + 5 workers**, מריץ עליו שלבים 1→2→3,
כותב הכל ל-`gs://`, ומוחק את הקלאסטר בסוף — גם אם משהו נכשל באמצע.

## 3. למשוך את התוצאות ולבנות את התוצרים

הסקריפט מדפיס בסוף את הפקודות המדויקות. בגדול:

```bash
gcloud storage cp -r gs://porto-taxi-project-bf990986/results/<STAMP>/* output/
python tools/validate_results.py output/stage3_subroutes.json   # ביקורת
python tools/build_subroute_maps.py                              # מפה
python tools/build_stage3_notebook.py                            # מחברת Colab
node   tools/build_methods_deck.js                               # מצגת
```

---

## בלי דאטהסט בכלל — בדיקה שהכל עובד

```bash
./run_local.sh --synthetic
```

מייצר נתונים סינתטיים עם מסלולים מתוכננים ידועים, מריץ את הפייפליין האמיתי,
ומאמת את התוצאה. לוקח כ-4 דקות.

---

## מה עוד נשאר אחרי ההרצה

- להריץ את `notebooks/stage3_colab_enterprise.ipynb` ב-**Colab Enterprise**
  (Vertex AI → Colab Enterprise → Notebooks — לא Colab הרגיל),
  ולשמור אותה **עם ה-outputs**
- לצלם את דוח העלויות מ-Billing → Reports (הדרישה אומרת שניצול התקציב משפיע על הציון)
- לשכתב את הודעת הקומיט `7aaf7d3` ("All fabrication removed")
- להעלות את הקוד למודל יום לפני ההגנה

## אם יצירת הקלאסטר נכשלת ב-ZONE_RESOURCE_POOL_EXHAUSTED

זה לא באג בקוד — זה אומר שאין כרגע מכונות פנויות באזור. שתי דרכים:

```bash
# 1. לנסות אזור אחר באותו region
ZONE=europe-west1-d bash scripts/run_pipeline_dataproc.sh

# 2. מכונות קטנות יותר (זמינות הרבה יותר, וגם זולות יותר)
MACHINE=e2-standard-2 bash scripts/run_pipeline_dataproc.sh
```

חשוב: `e2-standard-2` הוא 2 vCPU לכל node, כלומר 6 nodes = 12 vCPU במקום 24 —
נכנס בקלות במכסה של חשבון חדש. הריצה תהיה איטית יותר, אבל היא תסתיים.

לפני שמנסים שוב, כדאי לוודא שלא נשאר קלאסטר ישן שאוכל את המכסה:

```bash
gcloud dataproc clusters list --region=europe-west1
gcloud dataproc clusters delete <NAME> --region=europe-west1 --quiet
```

## הגדרות שאפשר לשנות

```bash
SUPPORT_PCT=0.10 bash scripts/run_pipeline_dataproc.sh   # סף X אחר
STAGES=3         bash scripts/run_pipeline_dataproc.sh   # רק שלב 3
KEEP_CLUSTER=1   bash scripts/run_pipeline_dataproc.sh   # לא למחוק את הקלאסטר
BUCKET=gs://...  bash scripts/run_pipeline_dataproc.sh   # דלי אחר
MACHINE=e2-standard-2 bash scripts/run_pipeline_dataproc.sh  # מכונות קטנות
ZONE=europe-west1-d   bash scripts/run_pipeline_dataproc.sh  # אזור אחר
```
