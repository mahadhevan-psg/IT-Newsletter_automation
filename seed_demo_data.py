import requests

API_URL = "http://127.0.0.1:8000/api/entries/ingest"

sample_submissions = [
    # 1. Research & Innovation
    {
        "form_id": "form_research",
        "raw_data": {
            "Timestamp": "2026-10-08 09:15:00",
            "Email Address": "dr.smith@ita.edu",
            "Research Subcategory": "Journal Publications",
            "Title of Publication / Patent / Project / Innovation": "Distributed Deep Learning Models for Natural Language Generation",
            "Authors / Investigators / Team Members": "Dr. John Smith, Dr. Sarah Jenkins",
            "Venue / Journal / Publisher / Funding Agency / Organization": "IEEE Transactions on Neural Networks",
            "Date of Publication / Award / Grant": "September 2026",
            "Impact Factor / Indexing (e.g., Scopus, Web of Science, IEEE, Q1/Q2)": "Impact Factor 10.2 / Scopus Q1",
            "DOI / Patent Number / Grant Amount / URL Link": "https://doi.org/10.1109/TNNLS.2026.109283",
            "Abstract / Executive Summary / Highlights": "Presents a novel gradient compression algorithm for multi-node deep learning clusters reducing inter-node communication latency by 45%.",
            "Photo Link (Google Drive / Cloud URL)": "https://drive.google.com/research_pub1.jpg",
            "Evidence / Certificate Link (Google Drive / Document URL)": "https://doi.org/10.1109/TNNLS.2026.109283"
        }
    },
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
            "DOI / Patent Number / Grant Amount / URL Link": "Grant Amount: $75,000",
            "Abstract / Executive Summary / Highlights": "Sanctioned 3-year research project focused on deploying IoT sensors and edge computing models to detect electrical network grid faults in real time.",
            "Evidence / Certificate Link (Google Drive / Document URL)": "https://drive.google.com/grant_letter.pdf"
        }
    },
    # 2. Faculty Achievements
    {
        "form_id": "form_faculty",
        "raw_data": {
            "Timestamp": "2026-10-08 10:00:00",
            "Email Address": "prof.varma@ita.edu",
            "Achievement Category": "Awards & Honors Received",
            "Faculty Full Name": "Prof. Rajesh Varma",
            "Title of Award / Certification / Keynote / Workshop": "Outstanding Educator & Researcher Award 2026",
            "Organization / Host Institution / Awarding Body": "Indian Society for Technical Education (ISTE)",
            "Date of Event / Award / Completion": "September 2026",
            "Level (International / National / State / University)": "National Level",
            "Description & Key Highlights": "Conferred the prestigious National Educator Award for excellence in computer science pedagogy and undergraduate research mentorship.",
            "Photo Link (Google Drive / Cloud URL)": "https://drive.google.com/prof_varma_award.jpg"
        }
    },
    {
        "form_id": "form_faculty",
        "raw_data": {
            "Timestamp": "2026-10-08 10:30:00",
            "Email Address": "ms.nair@ita.edu",
            "Achievement Category": "Invited Keynote / Expert Lectures Delivered",
            "Faculty Full Name": "Ms. P. Nair",
            "Title of Award / Certification / Keynote / Workshop": "Keynote Speaker on Cybersecurity & Zero Trust Frameworks",
            "Organization / Host Institution / Awarding Body": "International Cyber Defense Summit 2026",
            "Date of Event / Award / Completion": "October 2026",
            "Level (International / National / State / University)": "International Level",
            "Description & Key Highlights": "Delivered an invited expert keynote session on enterprise Zero Trust Architecture to over 500 cybersecurity professionals."
        }
    },
    # 3. Student Achievements
    {
        "form_id": "form_student",
        "raw_data": {
            "Timestamp": "2026-10-08 11:00:00",
            "Email Address": "rohan.sharma@ita.edu",
            "Student Achievement Category": "Hackathons & Coding Competitions",
            "Student Name(s)": "Rohan Sharma, Anita Roy, Kevin Patel",
            "Name of Competition / Award / Project / Event": "Global Hackathon Championship 2026",
            "Organizing Institute / Company / Body": "TechGiant Inc. & IEEE Computer Society",
            "Position / Rank / Prize / CTC (e.g. 1st Place, Cash Prize of $1000)": "1st Prize (Cash Award $5,000)",
            "Date of Event / Award": "October 2026",
            "Project Abstract / Achievement Details": "Secured 1st rank out of 350 international teams for constructing an autonomous AI disaster response drone dispatch dashboard.",
            "Photo Link (Google Drive / Cloud URL)": "https://drive.google.com/hackathon_win.jpg",
            "Certificate / Proof Link": "https://drive.google.com/cert_hackathon.pdf"
        }
    },
    # 4. Industry & Outreach
    {
        "form_id": "form_industry",
        "raw_data": {
            "Timestamp": "2026-10-08 11:30:00",
            "Email Address": "outreach.coord@ita.edu",
            "Outreach Category": "MoUs Signed & Industrial Collaborations",
            "Coordinator / Faculty Name": "Dr. S. Kulkarni",
            "Title of Event / Visit / MoU Partner": "Strategic Academic MoU with CloudTech Systems",
            "Company / Organization / Alumni Details": "CloudTech Systems India Pvt Ltd",
            "Date of Event / Execution": "September 2026",
            "Target Audience & Number of Participants": "Department of IT Faculty & Students",
            "Executive Summary & Outcomes": "Signed an MoU establishing a specialized Cloud Computing Center of Excellence in the department with $20,000 industry hardware sponsorship."
        }
    },
    # 5. Departmental Highlights
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
            "Total Participants Count": "Nvidia RTX Workstations (40 Units)",
            "Event Overview & Highlights": "Upgraded departmental computing facility with 40 high-end GPU workstations dedicated to Deep Learning, Computer Vision, and Data Analytics labs."
        }
    }
]

def seed():
    print("Seeding demo data into Newsletter Automation System...")
    for sub in sample_submissions:
        r = requests.post(API_URL, json=sub)
        print("Ingested:", r.status_code, r.json()["entry_id"])

    # Auto-approve all entries and spotlight top items
    entries = requests.get("http://127.0.0.1:8000/api/entries").json()
    for idx, e in enumerate(entries):
        is_featured = (idx in [0, 2, 4])
        requests.post(f"http://127.0.0.1:8000/api/entries/{e['entry_id']}/status", json={
            "approval_status": "Approved",
            "featured_flag": is_featured,
            "performer": "ChiefEditor"
        })
    print("Demo data seeded and approved successfully!")

if __name__ == "__main__":
    seed()
