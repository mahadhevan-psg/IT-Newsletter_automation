import os
import requests

API_URL = "http://127.0.0.1:8000/api/entries/ingest"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HACKATHON_IMG = os.path.join(BASE_DIR, "output", "demo_images", "hackathon_win.jpg")
FACULTY_IMG = os.path.join(BASE_DIR, "output", "demo_images", "prof_award.jpg")
MOU_IMG = os.path.join(BASE_DIR, "output", "demo_images", "mou_signing.jpg")

sample_submissions = [
    # 1. Research & Innovation - Journal Publication (Tier 3 Academic Digest)
    {
        "form_id": "form_research",
        "raw_data": {
            "Timestamp": "2026-10-08 09:15:00",
            "Email Address": "dr.smith@ita.edu",
            "Research Subcategory": "Journal Publications",
            "Title of Publication / Patent / Project / Innovation": "Distributed Deep Learning Models for Natural Language Generation",
            "Authors / Investigators / Team Members": "Dr. John Smith, Dr. Sarah Jenkins",
            "Venue / Journal / Publisher / Funding Agency / Organization": "IEEE Transactions on Neural Networks and Learning Systems",
            "Date of Publication / Award / Grant": "September 2026",
            "Impact Factor / Indexing (e.g., Scopus, Web of Science, IEEE, Q1/Q2)": "Impact Factor 10.2 / Scopus Q1",
            "Key Impact Badge / Metric": "Scopus Q1",
            "DOI / Patent Number / Grant Amount / URL Link": "https://doi.org/10.1109/TNNLS.2026.109283",
            "Abstract / Executive Summary / Highlights": "Presents a novel gradient compression algorithm for multi-node deep learning clusters, reducing inter-node communication latency by 45% without accuracy loss.",
            "Photo Link (Google Drive / Cloud URL)": "",
            "Evidence / Certificate Link (Google Drive / Document URL)": "https://doi.org/10.1109/TNNLS.2026.109283",
            "Is this a Landmark / Milestone Achievement?": "No (Standard Entry)"
        }
    },
    # 2. Research & Innovation - Funded Grant (Tier 1 Spotlight Hero Story)
    {
        "form_id": "form_research",
        "raw_data": {
            "Timestamp": "2026-10-08 09:45:00",
            "Email Address": "dr.kulkarni@ita.edu",
            "Research Subcategory": "Funded Research Projects",
            "Title of Publication / Patent / Project / Innovation": "AI-Powered Smart Grid Monitoring & Anomaly Detection System",
            "Authors / Investigators / Team Members": "Dr. S. Kulkarni (PI), Prof. R. Varma (Co-PI)",
            "Venue / Journal / Publisher / Funding Agency / Organization": "Department of Science & Technology (DST)",
            "Date of Publication / Award / Grant": "October 2026",
            "Impact Factor / Indexing (e.g., Scopus, Web of Science, IEEE, Q1/Q2)": "DST National Research Grant",
            "Key Impact Badge / Metric": "DST Grant: ₹45 Lakhs",
            "DOI / Patent Number / Grant Amount / URL Link": "Grant Amount: $75,000 (₹45,00,000)",
            "Abstract / Executive Summary / Highlights": "A prestigious 3-year national research project sanction focused on deploying synchronized IoT edge sensors and transformers to predict electrical power grid failures in real-time.",
            "Photo Link (Google Drive / Cloud URL)": "",
            "Evidence / Certificate Link (Google Drive / Document URL)": "https://dst.gov.in/grants/2026/EE-9821",
            "Is this a Landmark / Milestone Achievement?": "Yes (Nominate for Spotlight Feature)"
        }
    },
    # 3. Faculty Achievements - National Award (Tier 1 Spotlight Hero Story with Photo)
    {
        "form_id": "form_faculty",
        "raw_data": {
            "Timestamp": "2026-10-08 10:00:00",
            "Email Address": "prof.varma@ita.edu",
            "Achievement Category": "Awards & Honors Received",
            "Faculty Full Name": "Prof. Rajesh Varma",
            "Title of Award / Certification / Keynote / Workshop": "Outstanding National Educator & Pedagogy Excellence Award 2026",
            "Organization / Host Institution / Awarding Body": "Indian Society for Technical Education (ISTE)",
            "Date of Event / Award / Completion": "September 2026",
            "Level (International / National / State / University)": "National Level",
            "Key Impact Badge / Metric": "National ISTE Award",
            "Description & Key Highlights": "Conferred the prestigious National Educator Award during the 54th Annual ISTE Convention for ground-breaking curriculum design in Cloud Computing and undergraduate research mentorship.",
            "Photo Link (Google Drive / Cloud URL)": FACULTY_IMG,
            "Photo Caption & Persons in Image": "Prof. Rajesh Varma receiving the National Educator Trophy from the Chairman of ISTE",
            "Evidence / Certificate Link (Google Drive URL)": "https://isteonline.in/awards/2026/prof_varma.pdf",
            "Is this a Landmark / Milestone Achievement?": "Yes (Nominate for Spotlight Feature)"
        }
    },
    # 4. Faculty Achievements - Keynote (Tier 2 Visual Story Card)
    {
        "form_id": "form_faculty",
        "raw_data": {
            "Timestamp": "2026-10-08 10:30:00",
            "Email Address": "ms.nair@ita.edu",
            "Achievement Category": "Invited Keynote / Expert Lectures Delivered",
            "Faculty Full Name": "Ms. P. Nair",
            "Title of Award / Certification / Keynote / Workshop": "Keynote Lecture on Cybersecurity & Zero Trust Frameworks",
            "Organization / Host Institution / Awarding Body": "International Cyber Defense Summit 2026",
            "Date of Event / Award / Completion": "October 2026",
            "Level (International / National / State / University)": "International Level",
            "Key Impact Badge / Metric": "Keynote Speaker",
            "Description & Key Highlights": "Delivered an invited expert keynote address on enterprise Zero Trust Architecture to over 500 cybersecurity practitioners and C-suite executives.",
            "Photo Link (Google Drive / Cloud URL)": "",
            "Photo Caption & Persons in Image": "",
            "Evidence / Certificate Link (Google Drive URL)": "https://cyberdefense2026.org/speakers/p-nair",
            "Is this a Landmark / Milestone Achievement?": "No (Standard Entry)"
        }
    },
    # 5. Student Achievements - Hackathon Winners (Tier 1 Spotlight Hero Story with Photo)
    {
        "form_id": "form_student",
        "raw_data": {
            "Timestamp": "2026-10-08 11:00:00",
            "Email Address": "rohan.sharma@ita.edu",
            "Student Achievement Category": "Hackathons & Coding Competitions",
            "Student Name(s)": "Rohan Sharma, Anita Roy, Kevin Patel (Dept of IT)",
            "Name of Competition / Award / Project / Event": "Global Smart Cities Hackathon Championship 2026",
            "Organizing Institute / Company / Body": "TechGiant Inc. & IEEE Computer Society",
            "Position / Rank / Prize / CTC (e.g. 1st Place, Cash Prize of $1000)": "1st Prize (Cash Award $5,000 / ₹4,10,000)",
            "Key Impact Badge / Metric": "1st Prize ($5,000)",
            "Date of Event / Award": "October 2026",
            "Project Abstract / Achievement Details": "Secured 1st rank among 350+ international university teams by developing an autonomous AI disaster dispatch drone management system capable of optimizing medical kit deliveries during flood relief operations.",
            "Photo Link (Google Drive / Cloud URL)": HACKATHON_IMG,
            "Photo Caption & Persons in Image": "Left to Right: Rohan Sharma, Anita Roy, Kevin Patel holding the 1st Place Hackathon Trophy",
            "Certificate / Proof Link": "https://globalhackathon.io/winners/2026/team-it-ita",
            "Is this a Landmark / Milestone Achievement?": "Yes (Nominate for Spotlight Feature)"
        }
    },
    # 6. Industry & Outreach - Strategic MoU (Tier 2 Visual Story Card with Photo)
    {
        "form_id": "form_industry",
        "raw_data": {
            "Timestamp": "2026-10-08 11:30:00",
            "Email Address": "outreach.coord@ita.edu",
            "Outreach Category": "MoUs Signed & Industrial Collaborations",
            "Coordinator / Faculty Name": "Dr. S. Kulkarni",
            "Title of Event / Visit / MoU Partner": "Strategic Academic MoU with CloudTech Systems India",
            "Company / Organization / Alumni Details": "CloudTech Systems India Pvt Ltd",
            "Date of Event / Execution": "September 2026",
            "Target Audience & Number of Participants": "Department of IT Faculty & 120 Students",
            "Key Impact Badge / Metric": "MoU Signed (CoE Setup)",
            "Executive Summary & Outcomes": "Executed a 3-year comprehensive MoU establishing a dedicated Cloud Computing Center of Excellence in the department, including hardware sponsorship and internship tracks for students.",
            "Photo Link (Google Drive / Cloud URL)": MOU_IMG,
            "Photo Caption & Persons in Image": "MoU Signing Ceremony between Dept of IT Leadership and CloudTech Directors",
            "Event Report / Brochure Link": "https://ita.edu/outreach/cloudtech-mou-2026",
            "Is this a Landmark / Milestone Achievement?": "No (Standard Entry)"
        }
    },
    # 7. Departmental Highlights - High Performance Computing Lab (Tier 2 Visual Story Card)
    {
        "form_id": "form_departmental",
        "raw_data": {
            "Timestamp": "2026-10-08 12:00:00",
            "Email Address": "hod.it@ita.edu",
            "Department Highlight Category": "Infrastructure & Lab Upgrades",
            "Convener / Coordinator Name": "Dr. A. Sharma (HOD)",
            "Title of Event / Upgrade / Milestone": "Inauguration of Advanced High-Performance AI Computing Lab",
            "Coordinators / Department Leads": "Dr. A. Sharma, Prof. R. Varma",
            "Dates & Duration": "October 2026",
            "Total Participants Count": "40 High-End Workstations",
            "Key Impact Badge / Metric": "Lab Upgrade (₹60 Lakhs)",
            "Event Overview & Highlights": "State-of-the-art computational facility established with 40 NVIDIA RTX AI workstations, high-throughput storage, and deep learning libraries to facilitate hands-on student coursework and research initiatives.",
            "Photo Link (Google Drive / Cloud URL)": "",
            "Photo Caption & Persons in Image": "",
            "Event Report / Flyer Link": "https://ita.edu/facilities/ai-lab-inauguration",
            "Is this a Landmark / Milestone Achievement?": "No (Standard Entry)"
        }
    }
]

def seed():
    print("Seeding demo data into Newsletter Automation System...")
    for sub in sample_submissions:
        r = requests.post(API_URL, json=sub)
        print("Ingested:", r.status_code, r.json()["entry_id"])

    # Auto-approve all entries and preserve spotlight flags
    entries = requests.get("http://127.0.0.1:8000/api/entries").json()
    for e in entries:
        requests.post(f"http://127.0.0.1:8000/api/entries/{e['entry_id']}/status", json={
            "approval_status": "Approved",
            "featured_flag": bool(e.get("featured_flag")),
            "performer": "ChiefEditor"
        })
    print("Demo data seeded and approved successfully!")

if __name__ == "__main__":
    seed()
