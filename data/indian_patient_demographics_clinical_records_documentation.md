# Indian Patient Demographics and Clinical Records Dataset

## Dataset name

Indian Patient Demographics and Clinical Records Dataset

## Description

A completely fictional adult Indian patient cohort created for MedDataHub and SynthMed upload, profiling, ETL, data-quality, synthetic-generation, comparison and privacy-testing workflows. Every person, address, hospital, doctor and contact detail is invented. No real patient record or real contact information is included.

## Files

- Dataset: `indian_patient_demographics_clinical_records.csv`
- Generator: `../scripts/generate_indian_patient_dataset.py`
- Reference date for age: `2026-06-30`
- Deterministic random seed: `20261122`

## Size

- Records: **1,000**
- Columns: **46**
- Missing values: **0** across all 46,000 cells
- Encoding: UTF-8 with BOM, CRLF line endings, no index column

## Column dictionary

| # | Column | Type | Unit / format | Notes |
| --- | --- | --- | --- | --- |
| 1 | Patient_ID | string | `PAT-000001` ... `PAT-001000` | Unique |
| 2 | Full_Name | string | Given name + surname | Fictional; gender-consistent name pool |
| 3 | Date_of_Birth | date | `YYYY-MM-DD` | Consistent with `Age` at reference date |
| 4 | Age | integer | years | 18 to 65 at `2026-06-30` |
| 5 | Gender | category | `Male`, `Female` | Drives sex-specific reference assumptions |
| 6 | Phone_Number | string | `+91-00000-NNNNN` | Deliberately non-dialable placeholder |
| 7 | Email | string | `name@example.com` | Reserved example domain |
| 8 | House_Number | string | `Flat 12`, `No. 45`, `House 7B` | Fictional |
| 9 | Street_Name | string | text | Fictional street name |
| 10 | Area | string | text | Locality within the city |
| 11 | City | category | text | 18 Indian cities |
| 12 | District | string | text | Consistent with city and state |
| 13 | State | string | text | Consistent with city and district |
| 14 | Country | constant | `India` | All records |
| 15 | Pincode | string | 6 digits | Indian PIN-code format |
| 16 | Blood_Group | category | `A+`, `A-`, `B+`, `B-`, `AB+`, `AB-`, `O+`, `O-` | Fixed vocabulary |
| 17 | Height_cm | numeric | cm | Integer |
| 18 | Weight_kg | numeric | kg | One decimal |
| 19 | BMI | numeric | kg/m² | One decimal; derived from height and weight |
| 20 | Systolic_BP_mmHg | numeric | mmHg | 90 to 120; always greater than diastolic |
| 21 | Diastolic_BP_mmHg | numeric | mmHg | 60 to 80 |
| 22 | Heart_Rate_bpm | numeric | beats/min | 60 to 100 |
| 23 | Body_Temperature_C | numeric | °C | 36.5 to 37.3 |
| 24 | SpO2_Percentage | numeric | % | 95 to 100 |
| 25 | Respiratory_Rate_bpm | numeric | breaths/min | 12 to 18 |
| 26 | Fasting_Blood_Glucose_mg_dL | numeric | mg/dL | 70 to 99, fasting |
| 27 | Haemoglobin_g_dL | numeric | g/dL | Sex-specific interval |
| 28 | Total_Cholesterol_mg_dL | numeric | mg/dL | Derived from HDL, LDL and triglycerides |
| 29 | HDL_Cholesterol_mg_dL | numeric | mg/dL | Sex-specific interval |
| 30 | LDL_Cholesterol_mg_dL | numeric | mg/dL | 65 to 95 |
| 31 | Triglycerides_mg_dL | numeric | mg/dL | 60 to 140 |
| 32 | Creatinine_mg_dL | numeric | mg/dL | Sex-specific interval |
| 33 | Existing_Conditions | category | text | Fixed catalogue; not inferred from measurements |
| 34 | Allergies | category | text | Fixed catalogue |
| 35 | Current_Medications | category | text | Mapped from `Existing_Conditions` |
| 36 | Family_Medical_History | category | text | Fixed catalogue |
| 37 | Hospital_ID | string | `H001` ... `H008` | Consistent with hospital name |
| 38 | Hospital_Name | string | text | Fictional hospital |
| 39 | Department | category | text | Consistent with hospital and doctor |
| 40 | Doctor_Name | string | `Dr. ...` | Fictional; consistent with hospital and department |
| 41 | Visit_ID | string | `VIS-000001` ... `VIS-001000` | Unique |
| 42 | Visit_Date | date | `YYYY-MM-DD` | 2025-01-01 to 2026-06-30; after date of birth |
| 43 | Visit_Type | category | text | Fixed catalogue |
| 44 | Diagnosis | category | text | Fixed visit-reason catalogue; not derived from measurements |
| 45 | Risk_Level | category | `Low`, `Moderate`, `High` | Assigned from a fixed catalogue |
| 46 | Consultation_Status | category | `Completed`, `Cancelled`, `No Show` | Fixed catalogue |

## Configured adult reference intervals and sources

These are explicit demonstration intervals for a healthy adult cohort only. They are **not** universal reference intervals, not pregnancy- or paediatric-specific, not adjusted for altitude, renal disease or medication, and not valid for clinical decisions. Where a published source gives a wider interval, the configured range is a deliberately interior subrange chosen to avoid implausible extremes; no interval is presented as a new clinical reference range.

| Measurement | Configured generator interval | Published interval used as source | Source |
| --- | --- | --- | --- |
| Systolic BP | 90–120 mmHg, with systolic > diastolic | Normal adult BP 90/60 to 120/80 mmHg | MedlinePlus, *Vital signs* |
| Diastolic BP | 60–80 mmHg | Normal adult BP 90/60 to 120/80 mmHg | MedlinePlus, *Vital signs* |
| Fasting blood glucose | 70–99 mg/dL | Fasting plasma glucose 70–99 mg/dL | ABIM, *Laboratory Reference Ranges* |
| Heart rate | 60–100 bpm | Resting adult pulse 60–100 bpm | MedlinePlus, *Vital signs* |
| Body temperature | 36.5–37.3 °C | Adult temperature 36.5–37.3 °C | MedlinePlus, *Vital signs* |
| SpO2 | 95–100% | Adult oxygen saturation 95–100% | ATI, *Vital Signs Reference Ranges* |
| Respiratory rate | 12–18 breaths/min | Adult breathing 12–18 breaths/min | MedlinePlus, *Vital signs* |
| Haemoglobin, male | 13.5–17.5 g/dL | Male 13.5–17.5 g/dL | NBME / MercyOne adult normal ranges |
| Haemoglobin, female | 12.0–16.0 g/dL | Female 12.0–16.0 g/dL | NBME / MercyOne adult normal ranges |
| Total cholesterol | Derived; observed 122–180 mg/dL | Adult reference 0–199 mg/dL; desirable <200 mg/dL | Labcorp/Legacy lipid intervals; Mayo Clinic |
| HDL cholesterol, male | 40–59 mg/dL | Male >39 mg/dL; 40–59 borderline, ≥60 optimal | Labcorp/Legacy lipid intervals |
| HDL cholesterol, female | 50–59 mg/dL | Female >49 mg/dL; 50–59 borderline, ≥60 optimal | Labcorp/Legacy lipid intervals |
| LDL cholesterol | 65–95 mg/dL | Adult reference 0–99 mg/dL; <100 optimal | Labcorp/Legacy lipid intervals; Mayo Clinic |
| Triglycerides | 60–140 mg/dL | Normal <150 mg/dL | MedlinePlus / NBME |
| Creatinine, male | 0.6–1.2 mg/dL | Male 0.6–1.2 mg/dL | Medscape, *Lab Values, Normal Adult* |
| Creatinine, female | 0.5–1.1 mg/dL | Female 0.5–1.1 mg/dL | Medscape, *Lab Values, Normal Adult* |
| BMI | 18.6–24.7 kg/m² | WHO adult normal weight 18.5–24.9 kg/m²; WHO notes lower cutoffs for Asian populations | WHO |

Sex-specific rules: haemoglobin, HDL cholesterol and creatinine use the `Gender` value. No other measurement is sex-stratified in this demonstration.

## Internal consistency rules

- `Age` = completed years on `2026-06-30` from `Date_of_Birth`; all patients are 18–65.
- `BMI` = `Weight_kg / (Height_cm / 100)^2`, rounded to one decimal.
- `Total_Cholesterol` = `HDL + LDL + Triglycerides / 5`, rounded to the nearest mg/dL (Friedewald relation, valid here because triglycerides are <400 mg/dL).
- `Systolic_BP_mmHg` is always greater than `Diastolic_BP_mmHg`.
- `Patient_ID` and `Visit_ID` are unique.
- `Hospital_ID` maps to one `Hospital_Name`; each `(Hospital_ID, Department)` maps to one `Doctor_Name`.
- `Visit_Date` is after `Date_of_Birth` and not later than `2026-06-30`.
- Vital signs and laboratory values are always positive and inside the configured intervals.
- No clinical diagnosis is calculated from a vital sign or laboratory value.

## Missing-value summary

`MISSING_RATE = 0.0` in the generator. The delivered CSV has **0** blank cells. The constant can be raised in the generator if a college test needs a small, controlled missing-value percentage; any such change must be documented separately.

## Synthetic data disclaimer

This is synthetic data for software testing and demonstration only. It is not a real patient cohort, not clinically validated, not a source of medical advice, and must not be used for patient care. `example.com` addresses and `+91-00000-` phone numbers are deliberately non-contactable. The dataset provides no anonymity or differential-privacy guarantee.

## Data-generation assumptions

- Fixed reference date `2026-06-30` for age calculation; visits occur between `2025-01-01` and that date.
- Deterministic seed `20261122` makes regeneration reproducible.
- Given names are drawn from gender-consistent fictional Indian name pools; surnames are common Indian family names used only as fictional labels.
- Addresses combine fictional house and street details with real city, district, state and 6-digit PIN-code formats; no real individual's address is represented.
- Eight fictional hospitals and a fixed doctor directory keep hospital, department and doctor relationships consistent.
- Conditions, allergies, medications, family history, visit types, diagnosis labels, risk levels and consultation statuses come from fixed catalogues; medications are linked to conditions by a documented mapping.
- Values are drawn from the interior of the published intervals, avoiding extreme low or high measurements; no unit mixing occurs.
- CSV is written with UTF-8 BOM and CRLF line endings so it opens directly in Microsoft Excel; there is no index column.

## Validation summary

| Check | Result |
| --- | --- |
| Records | 1,000 |
| Columns | 46, exact required order |
| Unique `Patient_ID` | 1,000 |
| Unique `Visit_ID` | 1,000 |
| Blank cells | 0 |
| Age range | 18–65 |
| BMI range | 18.6–24.7 |
| Systolic BP range | 90–120 mmHg |
| Diastolic BP range | 60–80 mmHg |
| Total cholesterol range | 122–180 mg/dL |
| Distinct cities | 18 |
| Distinct hospitals | 8 |
| Hospital/doctor consistency | Passed |
| Friedewald consistency | Passed within 1 mg/dL |
| Excel-compatible CSV | Passed (UTF-8 BOM, CRLF, no index) |

## Sources

- MedlinePlus, *Vital signs*: https://medlineplus.gov/ency/article/002341.htm
- ATI, *Vital Signs Reference Ranges*: https://www.atitesting.com/docs/default-source/product-integration/engage/vital-signs-reference-ranges.pdf
- ABIM, *Laboratory Reference Ranges*: https://www.abim.org/media/e2wdwdqu/laboratory-reference-ranges.pdf
- NBME, *Laboratory Reference Values*: https://www.nbme.org/wp-content/uploads/2026/04/NBME_Laboratory_Reference_Values.pdf
- Medscape, *Lab Values, Normal Adult*: https://emedicine.medscape.com/article/2172316-overview
- Labcorp/Legacy, *Lipid Reference Intervals*: https://lhs.labqms.com/Files/1392/1393/32414/Publish/32414_4_08272024_114617_AM.pdf
- Mayo Clinic, *High cholesterol – Diagnosis and treatment*: https://www.mayoclinic.org/diseases-conditions/high-blood-cholesterol/diagnosis-treatment/drc-20350806
- Quest Diagnostics, *LDL Cholesterol Calculations*: https://www.questdiagnostics.com/healthcare-professionals/clinical-education-center/faq/faq164
- WHO, *Obesity and overweight*: https://www.who.int/news-room/fact-sheets/detail/obesity-and-overweight
