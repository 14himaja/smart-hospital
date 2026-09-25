"""Initial database seed script with valid doctor mappings and Indian emergency localization."""

import json
from datetime import datetime, date, timedelta
from typing import Optional
from app.db.connection import get_db_connection
from app.db.repositories.users import hash_password
from app.models import UserRole, DocumentType, AppointmentStatus


def seed_data_if_empty(db_path: Optional[str] = None) -> None:
    """Seed initial departments, doctors, slots, users, appointments, and knowledge base if empty."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM departments")
        if cursor.fetchone()[0] > 0:
            return  # Already seeded

        # 1. Seed Departments
        depts = [
            ("DEP-DERM", "Dermatology", "Skin, hair, and nail health, cosmetic dermatology, and skin allergy management.", "Building A, 2nd Floor, Wing B"),
            ("DEP-CARD", "Cardiology", "Comprehensive heart disease diagnostics, ECG, echocardiograms, and cardiac rehabilitation.", "Building B, 1st Floor, Heart Center"),
            ("DEP-ORTHO", "Orthopedics", "Bone and joint health, sports injuries, fractures, and spine care.", "Building A, Ground Floor"),
            ("DEP-PED", "Pediatrics", "Child wellness, vaccinations, neonatal care, and adolescent medicine.", "Building C, 3rd Floor"),
            ("DEP-RAD", "Radiology", "Diagnostic imaging including X-Ray, MRI, CT scans, and ultrasound.", "Building B, Basement Level 1")
        ]
        cursor.executemany("INSERT INTO departments VALUES (?, ?, ?, ?)", depts)

        # 2. Seed Doctors
        docs = [
            ("DOC-001", "Dr. Sarah Jenkins", "DEP-DERM", "Dermatology", "General & Cosmetic Dermatology", json.dumps(["Monday", "Wednesday", "Friday"]), 1200.0),
            ("DOC-002", "Dr. B. K. Sharma", "DEP-DERM", "Dermatology", "Pediatric Dermatology & Allergy", json.dumps(["Monday", "Tuesday", "Thursday"]), 1500.0),
            ("DOC-003", "Dr. Alan Vance", "DEP-CARD", "Cardiology", "Interventional Cardiology", json.dumps(["Tuesday", "Thursday", "Saturday"]), 2000.0),
            ("DOC-004", "Dr. Elena Rostova", "DEP-ORTHO", "Orthopedics", "Joint Replacement & Sports Medicine", json.dumps(["Monday", "Wednesday", "Thursday"]), 1800.0)
        ]
        cursor.executemany("INSERT INTO doctors VALUES (?, ?, ?, ?, ?, ?, ?)", docs)

        # 3. Seed Slots for next 7 days
        today = date.today()
        time_options = ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "14:00", "14:30", "15:00", "15:30", "16:00", "16:30"]
        weekday_map = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}
        slots = []
        for i in range(1, 14):
            slot_date = (today + timedelta(days=i)).isoformat()
            target_weekday = weekday_map[(today + timedelta(days=i)).weekday()]
            for doc in docs:
                doc_id, doc_name, _, dept_name, _, avail_json, _ = doc
                avail_days = json.loads(avail_json)
                if target_weekday in avail_days:
                    for t in time_options:
                        slot_id = f"SLOT-{doc_id}-{slot_date}-{t.replace(':', '')}"
                        slots.append((slot_id, doc_id, doc_name, dept_name, slot_date, t, 1))
        cursor.executemany("INSERT INTO slots VALUES (?, ?, ?, ?, ?, ?, ?)", slots)

        # 4. Seed Users
        now_str = datetime.utcnow().isoformat()
        users = [
            ("P1001", "Rahul Sharma", "rahul@example.com", "+91-9876543210", UserRole.PATIENT.value, 1, hash_password("password123"), now_str, json.dumps({"language": "English", "preferred_department": "Dermatology"})),
            ("P1002", "Priya Patel", "priya@example.com", "+91-9876543211", UserRole.PATIENT.value, 1, hash_password("password123"), now_str, json.dumps({"language": "English"})),
            ("D2001", "Dr. B. K. Sharma", "dr.b@hospital.org", None, UserRole.DOCTOR.value, 1, hash_password("doctorpass"), now_str, json.dumps({"language": "English"})),
            ("S3001", "Hospital Desk Staff", "staff@hospital.org", None, UserRole.STAFF.value, 1, hash_password("staffpass"), now_str, json.dumps({"language": "English"})),
            ("A4001", "Hospital Administrator", "admin@hospital.org", "+91-9999988888", UserRole.ADMIN.value, 1, hash_password("adminpass123"), now_str, json.dumps({"language": "English"}))
        ]
        cursor.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", users)

        # 5. Seed Past & Upcoming Appointments (Using ONLY Real Doctor IDs & Names)
        past_appts = [
            ("APPT-1001", "P1001", "DOC-002", "Dr. B. K. Sharma", "Dermatology", (today - timedelta(days=14)).isoformat(), "10:00", AppointmentStatus.COMPLETED.value, "Initial consultation for skin eczema. Prescribed topical ointment.", now_str),
            ("APPT-1002", "P1001", "DOC-001", "Dr. Sarah Jenkins", "Dermatology", (today + timedelta(days=2)).isoformat(), "11:30", AppointmentStatus.CONFIRMED.value, "Routine skin and allergy checkup.", now_str),
            ("APPT-1003", "P1002", "DOC-003", "Dr. Alan Vance", "Cardiology", (today + timedelta(days=5)).isoformat(), "14:00", AppointmentStatus.SCHEDULED.value, "Cardiovascular health evaluation.", now_str),
            ("APPT-1004", "P1002", "DOC-004", "Dr. Elena Rostova", "Orthopedics", (today - timedelta(days=7)).isoformat(), "09:00", AppointmentStatus.CANCELLED.value, "Joint pain consultation (cancelled by patient).", now_str)
        ]
        cursor.executemany("INSERT INTO appointments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", past_appts)

        # 6. Seed Documents for P1001
        doc_text = (
            "Patient: Rahul Sharma (P1001)\n"
            "Date: 2026-09-08\n"
            "Test: Complete Blood Count (CBC) & Serum IgE Panel\n"
            "Hemoglobin: 14.5 g/dL (Normal Range: 13.5 - 17.5)\n"
            "WBC: 6,800 /mcL (Normal Range: 4,500 - 11,000)\n"
            "Platelets: 250,000 /mcL (Normal Range: 150,000 - 450,000)\n"
            "Serum IgE: 240 IU/mL (Elevated, Normal < 100 IU/mL)\n"
            "Impression: Mild allergic diathesis corresponding to atopic dermatitis."
        )
        doc_summary = "Lab report indicates normal blood counts with elevated Serum IgE (240 IU/mL), consistent with mild allergic sensitivity / atopic dermatitis."
        doc_findings = json.dumps(["Normal Hemoglobin & Platelets", "Elevated Serum IgE (240 IU/mL)"])
        docs_seed = [
            ("DOC-LAB-101", "P1001", "Complete Blood Count & Allergy Panel", DocumentType.LAB_REPORT.value, (today - timedelta(days=13)).isoformat(), doc_text, doc_summary, doc_findings)
        ]
        cursor.executemany("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?)", docs_seed)

        # 7. Seed Public Hospital Policies & Knowledge
        kb = [
            ("Visiting Hours", "General hospital visiting hours are daily from 10:00 AM to 1:00 PM and 4:30 PM to 8:00 PM. In ICU units, visiting is restricted to 5:00 PM to 6:00 PM with a maximum of one visitor per patient."),
            ("Registration Requirements", "First-time patients must bring a government-issued photo ID (Aadhaar, Passport, or Driving License), insurance card if applicable, and previous medical prescriptions. Online registration provides a digital Patient ID (e.g. P1001) for swift kiosk check-in."),
            ("Dermatology Procedures", "The Dermatology department provides diagnostic skin allergy testing, mole evaluations, eczema management, cryotherapy, and light therapy. Routine consultations take approximately 20 minutes."),
            ("Cardiology Services & Location", "Cardiology is located in Building B, 1st Floor Heart Center. It handles chest pain evaluation, hypertension management, ECG, 2D Echo, and stress tests."),
            ("Emergency and Ambulatory Care", "Emergency trauma and acute care operates 24/7 at Gate 1 on the Ground Floor. For life-threatening emergencies, call the rapid ambulance service at 108 or national emergency helpline 112.")
        ]
        cursor.executemany("INSERT INTO knowledge_base (topic, content) VALUES (?, ?)", kb)
        conn.commit()
