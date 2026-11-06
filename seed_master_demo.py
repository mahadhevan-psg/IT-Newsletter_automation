"""Fill a RUNNING server with demo faculty, students, submissions and placements so the portal and diary have something to show.

    python run_server.py                      (in another terminal)
    python seed_test_logins.py                (once: creates the ADMIN01 / Test@1234 test admin)
    python seed_master_demo.py                (signs in as ADMIN01 / Test@1234)
    python seed_master_demo.py <admin-password> [http://127.0.0.1:8000]      (signs in as ADMIN instead)

Uses only the public API (the same uploads tutors use), so it also exercises the importers. Do NOT run against real data.
"""
import io
import json
import os
import sys

import openpyxl
import requests

BASE = (sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000").rstrip("/")
ADMIN_LOGIN = ("ADMIN", sys.argv[1]) if len(sys.argv) > 1 else ("ADMIN01", "Test@1234")
SPEC = json.load(open(os.path.join(os.path.dirname(__file__), "config", "master_forms.json"), encoding="utf-8"))


def book(headers, rows):
    wb = openpyxl.Workbook()
    wb.active.append(headers)
    for r in rows:
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def send(path, token, headers, rows, **form):
    r = requests.post(BASE + path, headers={"Authorization": f"Bearer {token}"}, data=form,
                      files={"file": ("d.xlsx", book(headers, rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    r.raise_for_status()
    return r.json()


def login(i, p):
    r = requests.post(BASE + "/api/auth/login", json={"id": i, "password": p})
    r.raise_for_status()
    return r.json()["token"]


def form_rows(form_id, dicts):
    """Rows keyed by master-DB field name -> list of cells in the form's column order (plus Timestamp, Email)."""
    qs = [q for q in SPEC["forms"][form_id]["questions"] if q["type"] != "section"]
    heads = ["Timestamp", "Email Address"] + [q["q"] for q in qs]
    rows = [[d.get("_ts", "2025-10-01 10:00:00"), d.get("_email", "")] + [d.get(q.get("key"), "") for q in qs] for d in dicts]
    return heads, rows


def main():
    admin = login(*ADMIN_LOGIN)
    auth = {"Authorization": f"Bearer {admin}"}
    fac = [["EMP001", "Dr. Priya Raman", "priya@demo.edu", "Professor"], ["EMP002", "Dr. Karthik Subbu", "karthik@demo.edu", "Associate Professor"],
           ["EMP003", "Dr. Meera Iyer", "meera@demo.edu", "Assistant Professor"], ["EMP004", "Dr. Arun Kumar", "arun@demo.edu", "Professor"],
           ["EMP005", "Dr. Lakshmi N", "lakshmi@demo.edu", "Associate Professor"], ["EMP006", "Dr. S. Venkat", "venkat@demo.edu", "Professor & HoD"]]
    res = send("/api/master/faculty/upload", admin, ["Employee ID", "Full Name", "Email", "Designation"], fac)
    creds = {c["emp_id"]: c["temp_password"] for c in res["credentials"]}
    classes = {c["class_code"]: c["class_id"] for c in requests.get(BASE + "/api/master/classes", headers=auth).json()}
    for code, emp in (("UG-G1-4", "EMP001"), ("UG-G1-3", "EMP002"), ("UG-G2-4", "EMP003")):
        requests.put(f"{BASE}/api/master/classes/{classes[code]}/tutor", json={"emp_id": emp}, headers=auth).raise_for_status()
    requests.put(f"{BASE}/api/master/faculty/EMP005/roles", json={"roles": [{"role": "PC", "programme": "UG", "grp": "G1"}]}, headers=auth)
    requests.put(f"{BASE}/api/master/faculty/EMP006/roles", json={"roles": [{"role": "HOD"}]}, headers=auth)

    names = ["Asha", "Ravi", "Meena", "Karan", "Divya", "Surya", "Nila", "Pranav", "Anitha", "Vijay", "Harini", "Gokul"]
    t = {e: login(e, creds[e]) for e in ("EMP001", "EMP002", "EMP003")}
    for emp, code, prefix in (("EMP001", "UG-G1-4", "22ITA"), ("EMP002", "UG-G1-3", "23ITA"), ("EMP003", "UG-G2-4", "22ITB")):
        send("/api/master/students/upload", t[emp], ["Roll No", "Full Name"],
             [[f"{prefix}{i + 1:02d}", f"{n} {code[-3:]}"] for i, n in enumerate(names)], class_id=str(classes[code]))

    heads, rows = form_rows("form_student", [
        {"_email": "priya@demo.edu", "_participants": "22ITA01\n22ITA02", "_lead_roll": "22ITA01", "is_team": "Team",
         "category": "Hackathons & Coding Competitions", "title": "Smart India Hackathon 2025", "organizer": "AICTE", "level": "National", "position": "Winner",
         "prize_amount": "100000", "result_date": "2025-09-12", "domain": "AI / Machine Learning", "mentor_emp_id": "EMP001 - Dr. Priya Raman",
         "abstract": "Built an AI triage assistant.", "is_landmark": "Yes (Nominate for Spotlight Feature)", "publish_permission": "Yes"},
        {"_email": "karthik@demo.edu", "_participants": "23ITA03", "_lead_roll": "23ITA03", "is_team": "Individual",
         "category": "Academic Excellence & Ranks", "title": "University Rank 3", "organizer": "Anna University", "level": "State", "position": "Rank 3",
         "result_date": "2025-08-20", "domain": "Other", "mentor_emp_id": "EMP002 - Dr. Karthik Subbu", "abstract": "Third university rank."},
        {"_email": "meera@demo.edu", "_participants": "22ITB05\n22ITB06", "_lead_roll": "22ITB06", "is_team": "Team",
         "category": "Technical Projects & Innovations", "title": "Smart Irrigation", "organizer": "IEEE Student Branch", "level": "Inter-college",
         "position": "2nd Prize", "prize_amount": "25000", "result_date": "2026-02-10", "domain": "IoT / Embedded", "mentor_emp_id": "EMP003 - Dr. Meera Iyer", "abstract": "IoT irrigation."}])
    print("student forms:", send("/api/master/forms/form_student/upload", admin, heads, rows))
    heads, rows = form_rows("form_research", [
        {"_email": "priya@demo.edu", "_submitter": "EMP001 - Dr. Priya Raman", "category": "Journal Publications", "title": "Federated Learning for Campus Analytics", "current_status": "Published",
         "_contributors": "EMP001 - Dr. Priya Raman\n22ITA01\nEXT - Dr. J. Smith - IIT Madras", "venue_publisher": "IEEE Access", "output_date": "2025-07-15",
         "indexing": "Scopus", "quartile": "Q1", "impact_factor": "3.9", "abstract": "A federated approach."},
        {"_email": "arun@demo.edu", "_submitter": "EMP004 - Dr. Arun Kumar", "category": "Funded Research Projects", "title": "Smart Campus IoT", "current_status": "Ongoing",
         "_contributors": "EMP004 - Dr. Arun Kumar", "venue_publisher": "DST", "output_date": "2025-11-01", "funding_status": "Funded", "funding_amount": "12 lakhs", "abstract": "Funded by DST."}])
    print("research:", send("/api/master/forms/form_research/upload", admin, heads, rows))
    heads, rows = form_rows("form_faculty", [{"_email": "lakshmi@demo.edu", "emp_id": "EMP005 - Dr. Lakshmi N", "category": "Awards & Honors Received", "title": "Best Teacher Award",
                                              "host_org": "Rotary Club", "level": "State", "start_date": "2025-09-05", "description": "State level teaching award."}])
    print("faculty:", send("/api/master/forms/form_faculty/upload", admin, heads, rows))
    heads, rows = form_rows("form_departmental", [{"_email": "venkat@demo.edu", "_submitter": "EMP006 - Dr. S. Venkat", "convener_emp_id": "EMP002 - Dr. Karthik Subbu", "category": "Workshops & FDPs Organized",
                                                   "title": "5-Day AI Workshop", "start_date": "2025-12-01", "participant_count": "120", "overview": "Hands-on AI workshop.", "_event_participants": "23ITA03"}])
    print("department:", send("/api/master/forms/form_departmental/upload", admin, heads, rows))
    heads, rows = form_rows("form_industry", [{"_email": "venkat@demo.edu", "_submitter": "EMP006 - Dr. S. Venkat", "lead_emp_id": "EMP006 - Dr. S. Venkat", "category": "MoUs Signed & Industrial Collaborations",
                                               "title": "MoU with Acme Technologies", "_partner": "Acme Technologies", "partner_type": "Industry", "start_date": "2025-10-10",
                                               "agreement_effective": "2025-10-10", "agreement_expiry": "2028-10-09", "actual_count": "80", "summary_outcomes": "Internship and training MoU."}])
    print("outreach:", send("/api/master/forms/form_industry/upload", admin, heads, rows))

    qs = [q for q in SPEC["placement"]["questions"] if q["type"] != "section"]
    def prow(**d):
        return [d.get(q["key"], "") for q in qs]
    heads = [q["q"] for q in qs]
    yes = "Yes - share anonymously with juniors"
    rows24 = [prow(roll_no="22ITA01", ay_id="2025-26", opt_status="Opted In", company="Acme Technologies", sector="Product", offer_type="FTE", package_lpa="12", job_role="SDE",
                   offer_status="Accepted", difficulty="Medium", rounds_count="4", round_details="Online test, 2 technical, HR", questions_asked="Graph problems, SQL joins",
                   result="Selected", interview_experience="Focus on data structures and project depth. Panel was friendly.", tips="Revise DBMS and practise medium LeetCode.", consent=yes),
              prow(roll_no="22ITA02", ay_id="2025-26", opt_status="Opted In", company="Acme Technologies", sector="Product", offer_type="Intern-Converted FTE", package_lpa="10", job_role="SDE",
                   intern_duration="6 months", intern_mode="Hybrid", intern_role="Backend intern", tech_stack="Java, Spring, Postgres", work_summary="Built billing APIs.", learnings="Code reviews and testing.",
                   rating="5", internship_experience="Great mentors; converted to FTE after 6 months.", consent=yes),
              prow(roll_no="22ITA03", ay_id="2025-26", opt_status="Opted In", company="Beta Soft", sector="IT Services", offer_type="FTE", package_lpa="4.5", job_role="Analyst", offer_status="Accepted",
                   difficulty="Easy", interview_experience="Aptitude + HR only.", consent=yes),
              prow(roll_no="22ITA04", ay_id="2025-26", opt_status="Opted Out", opt_out_reason="Higher studies"),
              prow(roll_no="22ITA05", ay_id="2025-26", opt_status="Opted In", company="Gamma Labs", sector="Startup", offer_type="FTE+Intern", package_lpa="8", stipend_per_month="20000", job_role="ML Engineer",
                   difficulty="Hard", questions_asked="System design, ML basics", interview_experience="Tough technical rounds.", tips="Know your projects deeply.", consent=yes)]
    rows23 = [prow(roll_no="22ITB01", ay_id="2024-25", opt_status="Opted In", company="Acme Technologies", sector="Product", offer_type="FTE", package_lpa="9", job_role="SDE", consent=yes),
              prow(roll_no="22ITB02", ay_id="2024-25", opt_status="Opted In", company="Beta Soft", sector="IT Services", offer_type="FTE", package_lpa="4", job_role="Analyst", consent=yes)]
    print("placements 25-26:", send("/api/master/placements/upload", admin, heads, rows24))
    print("placements 24-25:", send("/api/master/placements/upload", admin, heads, rows23))
    print(f"\nLogins - staff portal /portal/ : {ADMIN_LOGIN[0]}/{ADMIN_LOGIN[1] if ADMIN_LOGIN[0] != 'ADMIN' else '(your password)'}, "
          + ", ".join(f"{k}/{v}" for k, v in creds.items()))
    print("Student diary /diary/ : roll number 22ITA01 with password 22ITA01 (first sign-in), any of 22ITA01..22ITA12 / 23ITA01.. / 22ITB01..")


if __name__ == "__main__":
    main()
