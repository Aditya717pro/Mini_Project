from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 20261122
RECORD_COUNT = 1000
REFERENCE_DATE = date(2026, 6, 30)
MISSING_RATE = 0.0
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data"
CSV_PATH = OUTPUT_DIR / "indian_patient_demographics_clinical_records.csv"

COLUMNS = [
    "Patient_ID",
    "Full_Name",
    "Date_of_Birth",
    "Age",
    "Gender",
    "Phone_Number",
    "Email",
    "House_Number",
    "Street_Name",
    "Area",
    "City",
    "District",
    "State",
    "Country",
    "Pincode",
    "Blood_Group",
    "Height_cm",
    "Weight_kg",
    "BMI",
    "Systolic_BP_mmHg",
    "Diastolic_BP_mmHg",
    "Heart_Rate_bpm",
    "Body_Temperature_C",
    "SpO2_Percentage",
    "Respiratory_Rate_bpm",
    "Fasting_Blood_Glucose_mg_dL",
    "Haemoglobin_g_dL",
    "Total_Cholesterol_mg_dL",
    "HDL_Cholesterol_mg_dL",
    "LDL_Cholesterol_mg_dL",
    "Triglycerides_mg_dL",
    "Creatinine_mg_dL",
    "Existing_Conditions",
    "Allergies",
    "Current_Medications",
    "Family_Medical_History",
    "Hospital_ID",
    "Hospital_Name",
    "Department",
    "Doctor_Name",
    "Visit_ID",
    "Visit_Date",
    "Visit_Type",
    "Diagnosis",
    "Risk_Level",
    "Consultation_Status",
]

MALE_GIVEN_NAMES = [
    "Aarav", "Arjun", "Bhavesh", "Chetan", "Dhruv", "Farhan", "Ganesh", "Harsh",
    "Imran", "Ishaan", "Jatin", "Kabir", "Kiran", "Manish", "Nikhil", "Rahul",
    "Rajat", "Rohan", "Sameer", "Siddharth", "Tanmay", "Varun", "Vikram", "Vivaan",
    "Yash", "Arvind", "Dev", "Kunal", "Naveen", "Ravi", "Sagar", "Vijay",
]

FEMALE_GIVEN_NAMES = [
    "Aditi", "Ananya", "Asha", "Amina", "Bhavana", "Deepa", "Devika", "Diya",
    "Elena", "Gauri", "Hema", "Ira", "Jaya", "Kajal", "Kavya", "Lakshmi", "Maya",
    "Meera", "Nisha", "Pooja", "Priya", "Riya", "Sana", "Shreya", "Sneha",
    "Sonia", "Tara", "Usha", "Zoya", "Anjali", "Kavita", "Neha", "Rekha",
]

ALL_GIVEN_NAMES = MALE_GIVEN_NAMES + FEMALE_GIVEN_NAMES

SURNAMES = [
    "Agarwal", "Bansal", "Chavan", "Desai", "Fernandes", "Gupta", "Hegde", "Iyer",
    "Joshi", "Kapoor", "Kulkarni", "Mehta", "Nair", "Patel", "Qureshi", "Rao",
    "Reddy", "Sharma", "Singh", "Verma", "Bhatt", "Chatterjee", "Dutta", "Ghosh",
    "Khan", "Menon", "Mishra", "Pillai", "Saxena", "Tiwari", "Yadav", "Zaveri",
]

LOCATIONS = [
    ("Mumbai", "Mumbai Suburban", "Maharashtra", "4000", ("Andheri West", "Powai", "Borivali East")),
    ("Pune", "Pune", "Maharashtra", "4110", ("Kothrud", "Baner", "Shivajinagar")),
    ("Nagpur", "Nagpur", "Maharashtra", "4400", ("Dharampeth", "Civil Lines", "Hingna")),
    ("Bengaluru", "Bengaluru Urban", "Karnataka", "5600", ("Indiranagar", "Jayanagar", "Whitefield")),
    ("Hyderabad", "Hyderabad", "Telangana", "5000", ("Banjara Hills", "Gachibowli", "Secunderabad")),
    ("Chennai", "Chennai", "Tamil Nadu", "6000", ("T. Nagar", "Anna Nagar", "Velachery")),
    ("Kolkata", "Kolkata", "West Bengal", "7000", ("Salt Lake", "New Town", "Park Street")),
    ("Delhi", "New Delhi", "Delhi", "1100", ("Connaught Place", "Saket", "Rohini")),
    ("Jaipur", "Jaipur", "Rajasthan", "3020", ("Malviya Nagar", "C-Scheme", "Vaishali Nagar")),
    ("Ahmedabad", "Ahmedabad", "Gujarat", "3800", ("Satellite", "Vastrapur", "Navrangpura")),
    ("Lucknow", "Lucknow", "Uttar Pradesh", "2260", ("Gomti Nagar", "Hazratganj", "Alambagh")),
    ("Patna", "Patna", "Bihar", "8000", ("Kankarbagh", "Boring Road", "Rajiv Nagar")),
    ("Bhopal", "Bhopal", "Madhya Pradesh", "4620", ("MP Nagar", "Arera Colony", "Kolar Road")),
    ("Indore", "Indore", "Madhya Pradesh", "4520", ("Vijay Nagar", "Palasia", "Bhawarkua")),
    ("Kochi", "Ernakulam", "Kerala", "6820", ("Fort Kochi", "Kaloor", "Kakkanad")),
    ("Guwahati", "Kamrup Metropolitan", "Assam", "7810", ("Paltan Bazaar", "Dispur", "Chandmari")),
    ("Chandigarh", "Chandigarh", "Chandigarh", "1600", ("Sector 17", "Sector 22", "Sector 35")),
    ("Thiruvananthapuram", "Thiruvananthapuram", "Kerala", "6950", ("Kowdiar", "Vellayambalam", "Sreekaryam")),
]

STREET_NAMES = [
    "Nehru Road", "Gandhi Marg", "Lotus Lane", "River View Road", "Sector 12 Road",
    "Tube Well Road", "Station Road", "Lake View Street", "Ashoka Avenue",
    "Sarojini Naidu Marg", "Crescent Road", "Mandir Road", "Garden Street",
    "Main Bazaar Road", "Green Park Road", "Tagore Marg",
]

BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

CONDITION_MEDICATION = {
    "No Known Conditions": "No Current Medication",
    "Type 2 Diabetes": "Metformin 500 mg",
    "Hypertension": "Amlodipine 5 mg",
    "Asthma": "Salbutamol Inhaler",
    "Hypothyroidism": "Levothyroxine 50 mcg",
    "Osteoarthritis": "Paracetamol 500 mg",
    "Anaemia": "Iron Supplement",
    "Chronic Rhinitis": "Cetirizine 10 mg",
}

ALLERGIES = [
    "No Known Allergies", "Penicillin", "Sulfa Drugs", "Shellfish", "Dust Mite",
    "Pollen", "Latex", "Ibuprofen", "Peanut", "Contrast Dye",
]

FAMILY_HISTORY = [
    "None Reported", "Diabetes (Parent)", "Hypertension (Parent)",
    "Heart Disease (Parent)", "Asthma (Sibling)", "Cancer (Grandparent)",
    "Thyroid Disorder (Parent)", "Stroke (Grandparent)",
]

HOSPITALS = [
    ("H001", "Konkan Health Institute"),
    ("H002", "Deccan Care Hospital"),
    ("H003", "Coromandel Medical Centre"),
    ("H004", "Vindhya Multi-Speciality Hospital"),
    ("H005", "Sabarmati Institute of Health"),
    ("H006", "Doon Valley Clinical Centre"),
    ("H007", "Malabar Community Hospital"),
    ("H008", "Kaveri Institute of Medical Sciences"),
]

DEPARTMENTS = [
    "General Medicine", "Cardiology", "Dermatology", "Orthopaedics", "Diabetology",
    "Pulmonology", "Neurology", "Ophthalmology", "ENT", "Psychiatry",
    "Gastroenterology", "Rheumatology",
]

VISIT_TYPES = ["New Consultation", "Follow-up", "Routine Check-up", "Lab Review", "Teleconsultation"]
DIAGNOSES = [
    "Routine health check-up", "General fatigue evaluation", "Mild upper respiratory infection",
    "Blood pressure review", "Diabetes follow-up", "Asthma review", "Anaemia follow-up",
    "Muscle pain", "Headache evaluation", "Skin rash assessment", "Joint pain review",
    "Neck stiffness",
]
RISK_LEVELS = ["Low", "Moderate", "High"]
CONSULTATION_STATUSES = ["Completed", "Completed", "Completed", "Cancelled", "No Show"]


def age_on(birth_date: date, reference: date) -> int:
    return reference.year - birth_date.year - ((reference.month, reference.day) < (birth_date.month, birth_date.day))


def make_doctor_map() -> dict[tuple[str, str], str]:
    doctor_rng = random.Random(SEED + 1)
    result = {}
    for hospital_id, _ in HOSPITALS:
        for department in doctor_rng.sample(DEPARTMENTS, 4):
            for _ in range(2):
                result[(hospital_id, department)] = (
                    f"Dr. {doctor_rng.choice(ALL_GIVEN_NAMES)} {doctor_rng.choice(SURNAMES)}"
                )
    return result


DOCTOR_MAP = make_doctor_map()


def blank_if_missing(value: str, rng: random.Random) -> str:
    if rng.random() < MISSING_RATE:
        return ""
    return value


def build_row(index: int, rng: random.Random) -> dict[str, str]:
    patient_id = f"PAT-{index:06d}"
    visit_id = f"VIS-{index:06d}"
    gender = rng.choice(["Male", "Female"])
    male = gender == "Male"
    given = rng.choice(MALE_GIVEN_NAMES if male else FEMALE_GIVEN_NAMES)
    surname = rng.choice(SURNAMES)
    full_name = f"{given} {surname}"
    age = rng.randint(18, 65)
    lower = date(REFERENCE_DATE.year - age - 1, REFERENCE_DATE.month, REFERENCE_DATE.day) + timedelta(days=1)
    upper = date(REFERENCE_DATE.year - age, REFERENCE_DATE.month, REFERENCE_DATE.day)
    dob = lower + timedelta(days=rng.randint(0, (upper - lower).days))
    visit_date = date(2025, 1, 1) + timedelta(days=rng.randint(0, (REFERENCE_DATE - date(2025, 1, 1)).days))

    city, district, state, pin_prefix, areas = rng.choice(LOCATIONS)
    house = f"{rng.choice(('Flat', 'No.', 'House'))} {rng.randint(1, 240)}{rng.choice(('', 'A', 'B'))}"
    pincode = f"{pin_prefix}{rng.randint(1, 99):02d}"

    height = rng.randint(162, 185) if male else rng.randint(150, 175)
    target_bmi = rng.uniform(18.6, 24.7)
    weight = round(target_bmi * (height / 100) ** 2, 1)
    bmi = round(weight / (height / 100) ** 2, 1)

    diastolic = rng.randint(60, 80)
    systolic = max(rng.randint(90, 120), diastolic + 20)
    temperature = round(rng.uniform(36.5, 37.3), 1)
    haemoglobin = round(rng.uniform(13.5, 17.5) if male else rng.uniform(12.0, 16.0), 1)
    creatinine = round(rng.uniform(0.6, 1.2) if male else rng.uniform(0.5, 1.1), 2)
    hdl = rng.randint(40, 59) if male else rng.randint(50, 59)
    ldl = rng.randint(65, 95)
    triglycerides = rng.randint(60, 140)
    total_cholesterol = round(hdl + ldl + triglycerides / 5)

    condition = rng.choice(list(CONDITION_MEDICATION))
    hospital_id, hospital_name = rng.choice(HOSPITALS)
    department = rng.choice([dept for (hid, dept) in DOCTOR_MAP if hid == hospital_id])

    row = {
        "Patient_ID": patient_id,
        "Full_Name": full_name,
        "Date_of_Birth": dob.isoformat(),
        "Age": str(age_on(dob, REFERENCE_DATE)),
        "Gender": gender,
        "Phone_Number": f"+91-00000-{index:05d}",
        "Email": f"{given.lower()}.{surname.lower()}.{index:04d}@example.com",
        "House_Number": house,
        "Street_Name": rng.choice(STREET_NAMES),
        "Area": rng.choice(areas),
        "City": city,
        "District": district,
        "State": state,
        "Country": "India",
        "Pincode": pincode,
        "Blood_Group": rng.choice(BLOOD_GROUPS),
        "Height_cm": str(height),
        "Weight_kg": f"{weight:.1f}",
        "BMI": f"{bmi:.1f}",
        "Systolic_BP_mmHg": blank_if_missing(str(systolic), rng),
        "Diastolic_BP_mmHg": blank_if_missing(str(diastolic), rng),
        "Heart_Rate_bpm": blank_if_missing(str(rng.randint(60, 100)), rng),
        "Body_Temperature_C": blank_if_missing(f"{temperature:.1f}", rng),
        "SpO2_Percentage": blank_if_missing(str(rng.randint(95, 100)), rng),
        "Respiratory_Rate_bpm": blank_if_missing(str(rng.randint(12, 18)), rng),
        "Fasting_Blood_Glucose_mg_dL": blank_if_missing(str(rng.randint(70, 99)), rng),
        "Haemoglobin_g_dL": blank_if_missing(f"{haemoglobin:.1f}", rng),
        "Total_Cholesterol_mg_dL": blank_if_missing(str(total_cholesterol), rng),
        "HDL_Cholesterol_mg_dL": blank_if_missing(str(hdl), rng),
        "LDL_Cholesterol_mg_dL": blank_if_missing(str(ldl), rng),
        "Triglycerides_mg_dL": blank_if_missing(str(triglycerides), rng),
        "Creatinine_mg_dL": blank_if_missing(f"{creatinine:.2f}", rng),
        "Existing_Conditions": condition,
        "Allergies": rng.choice(ALLERGIES),
        "Current_Medications": CONDITION_MEDICATION[condition],
        "Family_Medical_History": rng.choice(FAMILY_HISTORY),
        "Hospital_ID": hospital_id,
        "Hospital_Name": hospital_name,
        "Department": department,
        "Doctor_Name": DOCTOR_MAP[(hospital_id, department)],
        "Visit_ID": visit_id,
        "Visit_Date": visit_date.isoformat(),
        "Visit_Type": rng.choice(VISIT_TYPES),
        "Diagnosis": rng.choice(DIAGNOSES),
        "Risk_Level": rng.choice(RISK_LEVELS),
        "Consultation_Status": rng.choice(CONSULTATION_STATUSES),
    }
    return row


def generate() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\r\n")
        writer.writeheader()
        for index in range(1, RECORD_COUNT + 1):
            writer.writerow(build_row(index, rng))
    return CSV_PATH


def validate() -> dict[str, object]:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == COLUMNS, "column list mismatch"
        rows = list(reader)

    assert len(rows) == RECORD_COUNT, f"expected {RECORD_COUNT} rows, got {len(rows)}"
    patient_ids = [row["Patient_ID"] for row in rows]
    visit_ids = [row["Visit_ID"] for row in rows]
    assert len(set(patient_ids)) == RECORD_COUNT, "duplicate Patient_ID"
    assert len(set(visit_ids)) == RECORD_COUNT, "duplicate Visit_ID"
    assert all(row["Patient_ID"].startswith("PAT-") for row in rows)
    assert all(row["Visit_ID"].startswith("VIS-") for row in rows)

    blanks = sum(1 for row in rows for value in row.values() if value == "")
    assert blanks == 0, f"unexpected blank cells: {blanks}"

    hospital_names = dict(HOSPITALS)
    sexes = {"Male", "Female"}
    for row in rows:
        assert row["Gender"] in sexes
        male = row["Gender"] == "Male"
        assert 18 <= int(row["Age"]) <= 65
        assert date.fromisoformat(row["Date_of_Birth"]) < date.fromisoformat(row["Visit_Date"]) <= REFERENCE_DATE
        assert age_on(date.fromisoformat(row["Date_of_Birth"]), REFERENCE_DATE) == int(row["Age"])

        height = int(row["Height_cm"])
        weight = float(row["Weight_kg"])
        bmi = float(row["BMI"])
        assert 18.5 <= bmi <= 24.9
        assert abs(round(weight / (height / 100) ** 2, 1) - bmi) <= 0.1

        systolic = int(row["Systolic_BP_mmHg"])
        diastolic = int(row["Diastolic_BP_mmHg"])
        assert 90 <= systolic <= 120 and 60 <= diastolic <= 80 and systolic > diastolic
        assert 60 <= int(row["Heart_Rate_bpm"]) <= 100
        assert 36.5 <= float(row["Body_Temperature_C"]) <= 37.3
        assert 95 <= int(row["SpO2_Percentage"]) <= 100
        assert 12 <= int(row["Respiratory_Rate_bpm"]) <= 18
        assert 70 <= int(row["Fasting_Blood_Glucose_mg_dL"]) <= 99
        assert 13.5 <= float(row["Haemoglobin_g_dL"]) <= 17.5 if male else 12.0 <= float(row["Haemoglobin_g_dL"]) <= 16.0
        assert (0.6 <= float(row["Creatinine_mg_dL"]) <= 1.2) if male else (0.5 <= float(row["Creatinine_mg_dL"]) <= 1.1)

        hdl = int(row["HDL_Cholesterol_mg_dL"])
        ldl = int(row["LDL_Cholesterol_mg_dL"])
        triglycerides = int(row["Triglycerides_mg_dL"])
        total_cholesterol = int(row["Total_Cholesterol_mg_dL"])
        assert 40 <= hdl <= 59 if male else 50 <= hdl <= 59
        assert 65 <= ldl <= 95
        assert 60 <= triglycerides <= 140
        assert 0 <= total_cholesterol <= 199
        assert abs(total_cholesterol - hdl - ldl - triglycerides / 5) <= 1

        assert hospital_names[row["Hospital_ID"]] == row["Hospital_Name"]
        assert (row["Hospital_ID"], row["Department"]) in DOCTOR_MAP
        assert DOCTOR_MAP[(row["Hospital_ID"], row["Department"])] == row["Doctor_Name"]
        assert row["Country"] == "India"
        assert row["Phone_Number"].startswith("+91-00000-")
        assert row["Email"].endswith("@example.com")
        assert len(row["Pincode"]) == 6 and row["Pincode"].isdigit()

    return {
        "records": len(rows),
        "columns": len(COLUMNS),
        "unique_patient_ids": len(set(patient_ids)),
        "unique_visit_ids": len(set(visit_ids)),
        "blank_cells": blanks,
        "age_range": (min(int(row["Age"]) for row in rows), max(int(row["Age"]) for row in rows)),
        "bmi_range": (min(float(row["BMI"]) for row in rows), max(float(row["BMI"]) for row in rows)),
        "systolic_range": (min(int(row["Systolic_BP_mmHg"]) for row in rows), max(int(row["Systolic_BP_mmHg"]) for row in rows)),
        "diastolic_range": (min(int(row["Diastolic_BP_mmHg"]) for row in rows), max(int(row["Diastolic_BP_mmHg"]) for row in rows)),
        "total_cholesterol_range": (min(int(row["Total_Cholesterol_mg_dL"]) for row in rows), max(int(row["Total_Cholesterol_mg_dL"]) for row in rows)),
        "cities": len({row["City"] for row in rows}),
        "hospitals": len({row["Hospital_ID"] for row in rows}),
    }


if __name__ == "__main__":
    path = generate()
    summary = validate()
    print(f"generated: {path}")
    for key, value in summary.items():
        print(f"{key}: {value}")
