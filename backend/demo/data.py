"""Synthetic content for the demo site. Everything here is invented: names, titles, numbers and companies' offers are
made up to look realistic, and none of it describes a real person or a real placement result."""

# (employee ID, name, designation, qualification). IDs 101..116; roles are assigned in seed.py
FACULTY = [
    ("EMP101", "Dr. S. Venkatesan", "Professor & Head", "Ph.D"), ("EMP102", "Dr. R. Lakshmi Priya", "Professor", "Ph.D"),
    ("EMP103", "Dr. K. Arunkumar", "Professor", "Ph.D"), ("EMP104", "Dr. M. Revathi", "Associate Professor", "Ph.D"),
    ("EMP105", "Dr. P. Karthikeyan", "Associate Professor", "Ph.D"), ("EMP106", "Dr. N. Sangeetha", "Associate Professor", "Ph.D"),
    ("EMP107", "Dr. V. Balaji", "Associate Professor", "Ph.D"), ("EMP108", "Dr. A. Meenakshi", "Assistant Professor (Sr. Gr.)", "Ph.D"),
    ("EMP109", "Mr. T. Surendran", "Assistant Professor (Sr. Gr.)", "M.E"), ("EMP110", "Dr. G. Anitha", "Assistant Professor (Sr. Gr.)", "Ph.D"),
    ("EMP111", "Ms. D. Pavithra", "Assistant Professor", "M.E"), ("EMP112", "Dr. S. Ramesh Babu", "Assistant Professor", "Ph.D"),
    ("EMP113", "Mr. L. Vignesh", "Assistant Professor", "M.Tech"), ("EMP114", "Ms. B. Janani", "Assistant Professor", "M.E"),
    ("EMP115", "Dr. C. Harikrishnan", "Associate Professor", "Ph.D"), ("EMP116", "Ms. R. Deepika", "Assistant Professor", "M.Tech"),
]
HOD = "EMP101"
COORDINATORS = [("EMP102", "UG", "G1"), ("EMP103", "UG", "G2"), ("EMP104", "PG", None)]
TUTORS = ["EMP105", "EMP106", "EMP107", "EMP108", "EMP109", "EMP110", "EMP111", "EMP112", "EMP113", "EMP114"]   # one per active class, in class order

FEMALE = ["Aarthi", "Abirami", "Akshaya", "Anjali", "Bhavana", "Chitra", "Deepa", "Divya", "Gayathri", "Harini", "Indhu", "Janani", "Kavya", "Keerthana",
          "Lavanya", "Madhumitha", "Meena", "Nandhini", "Nithya", "Pooja", "Priya", "Ramya", "Sandhya", "Shalini", "Sneha", "Sowmya", "Swetha", "Tharani",
          "Uma", "Vaishnavi", "Varsha", "Yamini"]
MALE = ["Abhinav", "Adithya", "Aravind", "Arjun", "Ashwin", "Balaji", "Bharath", "Dinesh", "Gokul", "Hari", "Jeeva", "Karthik", "Kishore", "Lokesh",
        "Manoj", "Naveen", "Nikhil", "Pranav", "Rahul", "Rohit", "Sabari", "Sanjay", "Santhosh", "Siva", "Surya", "Tamil", "Vignesh", "Vijay", "Vishal",
        "Yogesh", "Dhanush", "Mohan"]
SURNAMES = ["Subramanian", "Krishnan", "Raman", "Iyer", "Nair", "Menon", "Pillai", "Kumar", "Raj", "Murugan", "Selvam", "Natarajan", "Venkat", "Gopal",
            "Narayanan", "Sundaram", "Ganesh", "Prakash", "Ramesh", "Shankar", "Bose", "Rao", "Reddy", "Shetty", "Patel", "Sharma", "Verma", "Das",
            "Mohan", "Chandran", "Anand", "Balan", "Devi", "Lakshmanan", "Mani", "Rajan", "Saravanan", "Thangavel", "Velu", "Yadav"]

EXTERNAL_PEOPLE = [("Dr. R. Ramesh", "IIT Madras"), ("Dr. A. Fernandes", "NIT Trichy"), ("Dr. S. Kapoor", "IIIT Hyderabad"), ("Prof. M. Chen", "NUS Singapore"),
                   ("Dr. L. Okafor", "University of Leeds"), ("Dr. P. Banerjee", "IISc Bengaluru"), ("Dr. T. Nakamura", "Kyoto University"), ("Dr. V. Joshi", "BITS Pilani")]

TOPICS = ["federated learning", "graph neural networks", "blockchain", "edge computing", "explainable AI", "transformer models", "reinforcement learning",
          "digital twins", "zero-trust networks", "semantic web", "computer vision", "natural language processing", "anomaly detection", "serverless computing",
          "swarm intelligence", "knowledge graphs", "quantum-safe cryptography", "time-series forecasting"]
APPLICATIONS = ["smart campus analytics", "crop disease detection", "healthcare triage", "network intrusion detection", "traffic management", "e-learning personalisation",
                "supply chain traceability", "fake news detection", "energy-efficient IoT", "medical image diagnosis", "software defect prediction", "smart agriculture",
                "financial fraud detection", "disaster response", "low-resource language translation", "student performance prediction"]
APPROACHES = ["A Lightweight", "A Scalable", "An Explainable", "A Hybrid", "A Privacy-Preserving", "A Real-Time", "An Attention-Based", "A Cloud-Native", "A Federated"]

JOURNALS = [("IEEE Access", "IEEE Xplore"), ("Expert Systems with Applications", "Scopus"), ("Computers & Security", "Web of Science"), ("Applied Soft Computing", "Scopus"),
            ("Future Generation Computer Systems", "Web of Science"), ("Multimedia Tools and Applications", "Scopus"), ("Cluster Computing", "Web of Science"),
            ("Journal of Network and Computer Applications", "Scopus"), ("International Journal of Information Technology", "UGC-CARE"),
            ("Neural Computing and Applications", "Scopus"), ("Sensors", "Web of Science"), ("Journal of Ambient Intelligence and Humanized Computing", "Scopus")]
CONFERENCES = ["IEEE International Conference on Computing, Communication and Networking Technologies", "International Conference on Advanced Computing and Communication Systems",
               "International Conference on Intelligent Computing and Control Systems", "National Conference on Emerging Trends in Information Technology",
               "IEEE International Conference on Data Science and Engineering", "International Conference on Machine Learning and Applications",
               "National Symposium on Cyber Security and Digital Forensics", "International Conference on Cloud Computing and Big Data"]
PUBLISHERS = ["Springer", "CRC Press", "Elsevier", "Wiley", "Taylor & Francis", "Narosa Publishing"]
AGENCIES = ["DST-SERB", "AICTE", "DRDO", "TNSCST", "UGC", "ICMR", "MeitY", "DST-TDT"]
CLIENTS = ["a Coimbatore textile exporter", "a regional hospital group", "a logistics start-up", "a state-run utility", "an automobile component maker", "a fintech start-up"]

AWARDS = ["Best Teacher Award", "Outstanding Researcher Award", "Young Faculty Excellence Award", "Best Paper Award", "Innovative Teaching Practices Award", "Mentor of the Year",
          "Distinguished Reviewer Award", "Best Project Guide Award"]
AWARD_BODIES = ["Rotary Club of Coimbatore", "Institution of Engineers (India)", "Computer Society of India", "ISTE Tamil Nadu", "IEEE Madras Section", "Tamil Nadu Science Council"]
CERTIFICATIONS = ["NPTEL: Cloud Computing (Elite + Silver)", "NPTEL: Deep Learning (Elite)", "AWS Certified Solutions Architect - Associate", "Google Cloud Professional Data Engineer",
                  "Oracle Certified Professional: Java SE", "Microsoft Certified: Azure Fundamentals", "NPTEL: Software Testing (Elite + Gold)", "Certified Ethical Hacker (CEH)"]
TALKS = ["Generative AI in the classroom", "Responsible AI and fairness", "Securing cloud-native applications", "Research methodology for young scholars", "Data structures made visual",
         "Career paths in cyber security", "Building reliable ML pipelines", "Open source for students"]
INSTITUTIONS = ["Kongu Engineering College", "Sri Krishna College of Engineering", "Anna University Regional Campus", "PSG Institute of Technology and Applied Research",
                "Amrita Vishwa Vidyapeetham", "SASTRA Deemed University", "Government College of Technology", "NIT Tiruchirappalli"]
PROFESSIONAL_ROLES = ["Member, Board of Studies (Information Technology)", "Reviewer, IEEE Transactions on Education", "Editorial board member, Journal of Applied Computing",
                      "Life member, Computer Society of India", "Senior member, IEEE", "Technical programme committee member, ICACCS"]
FDP_TOPICS = ["Artificial Intelligence for Teachers", "Outcome Based Education and Accreditation", "Cyber Security and Digital Forensics", "Research Writing and Publishing",
              "Cloud and DevOps Practices", "Data Analytics with Python"]

WORKSHOPS = ["Hands-on Workshop on Generative AI", "FDP on Cloud-Native Application Development", "Workshop on Cyber Security Essentials", "Five-Day FDP on Machine Learning Operations",
             "Workshop on Full-Stack Development", "Data Science Bootcamp", "Workshop on Competitive Programming", "FDP on Research and Innovation Ecosystem"]
CONFERENCES_ORG = ["National Conference on Intelligent Computing", "International Conference on Smart Systems", "Symposium on Emerging Technologies in IT", "National Level Technical Symposium"]
INFRA = [("AI and Machine Learning Laboratory", "Twenty GPU workstations, a shared training server and licensed tools"), ("Cyber Security Laboratory", "An isolated network range for attack and defence exercises"),
         ("Cloud Computing Laboratory", "A private cloud with sixty virtual machines for student projects"), ("IoT and Embedded Systems Laboratory", "Sensor kits, development boards and a small gateway network")]
CLUBS = ["Coding Club weekly contest series", "Cyber Security Club capture-the-flag night", "Open Source Club contribution drive", "AI Club paper reading group", "Entrepreneurship Cell idea pitch day"]
MILESTONES = ["NBA accreditation renewed for the B.Tech programme", "Department ranked among the top institutions in the state ranking", "Hundredth industry-sponsored student project completed",
              "Placement season closes with the highest participation in five years"]
PARTNERS = [("Zoho Corporation", "Industry"), ("Freshworks", "Industry"), ("Thoughtworks", "Industry"), ("Bosch Global Software", "Industry"), ("Cognizant", "Industry"),
            ("Infosys", "Industry"), ("IIT Madras Research Park", "Academic institution"), ("Coimbatore Alumni Association", "Alumni"), ("Tamil Nadu Skill Development Corporation", "Government"),
            ("Rural Digital Literacy Trust", "NGO / Community")]
VISIT_PLACES = ["its Chennai development centre", "its Coimbatore campus", "its data centre", "its product engineering floor"]
OUTREACH_TALKS = ["Life as a product engineer", "How we test at scale", "From campus to cloud", "Building a career in data", "Mentoring session for final years"]

HACKATHONS = [("Smart India Hackathon", "Ministry of Education, Govt. of India"), ("HackWithInfy", "Infosys"), ("Flipkart GRiD", "Flipkart"), ("Google Solution Challenge", "Google Developer Student Clubs"),
              ("Smart Coimbatore Hackathon", "Coimbatore Smart City"), ("Hack4Good", "ACM Student Chapter"), ("Code Sprint 24", "IIT Madras Shaastra"), ("TCS CodeVita", "TCS")]
PROJECT_EVENTS = [("IEEE Student Project Expo", "IEEE Madras Section"), ("Tamil Nadu Student Innovation Fair", "TNSCST"), ("Inter-college Project Contest", "PSG Institute"),
                  ("Techfest Project Showcase", "IIT Bombay"), ("Smart Systems Expo", "CII")]
PROJECT_TITLES = ["Smart attendance with face recognition", "AI crop doctor mobile app", "Low-cost water quality monitor", "Campus bus tracking platform", "Sign-language translator",
                  "Phishing URL detector browser plugin", "Energy-aware server scheduler", "Voice-controlled lab assistant", "Blockchain certificate verifier", "Accessible e-learning portal"]
RANK_EVENTS = [("Anna University semester examinations", "Anna University"), ("University rank list", "Anna University"), ("Departmental toppers' list", "Department of IT")]
HIGHER_ED = [("Admitted to M.S. in Computer Science", "University of Texas at Dallas"), ("Admitted to M.Tech in Data Science", "IIT Madras"), ("GATE qualified, AIR under 1000", "IIT Roorkee (GATE)"),
             ("Admitted to M.S. in Cyber Security", "Northeastern University"), ("Admitted to MBA programme", "IIM Indore")]
SPORTS = [("Inter-college Chess Championship", "PSG College of Technology", "Sports"), ("Anna University Zonal Football Tournament", "Anna University", "Sports"),
          ("Inter-collegiate Debate Championship", "Loyola College", "Cultural"), ("Cultural Fest Dance Competition", "Amrita University", "Cultural"), ("State Level Badminton Meet", "TNBA", "Sports"),
          ("Short Film Contest", "Coimbatore Film Society", "Cultural")]
POSITIONS_WIN = ["Winner", "First Prize", "Runner-up", "Second Prize", "Third Prize", "Special Mention", "Finalist"]

COMPANIES = [  # name, sector, (min LPA, max LPA), weight, roles, stipend per month for interns
    ("TCS", "IT Services", (3.6, 7.0), 12, ["Systems Engineer", "Digital Engineer"], 15000), ("Infosys", "IT Services", (3.6, 9.5), 12, ["Systems Engineer", "Power Programmer"], 18000),
    ("Wipro", "IT Services", (3.5, 6.5), 8, ["Project Engineer", "Software Engineer"], 15000), ("Cognizant", "IT Services", (4.0, 6.8), 10, ["Programmer Analyst Trainee", "GenC Elevate"], 20000),
    ("Accenture", "IT Services", (4.5, 7.5), 8, ["Associate Software Engineer", "Advanced Associate"], 20000), ("Capgemini", "IT Services", (4.0, 7.5), 6, ["Analyst", "Senior Analyst"], 15000),
    ("Zoho", "Product", (6.0, 10.0), 6, ["Member Technical Staff"], 25000), ("Freshworks", "Product", (10.0, 18.0), 3, ["Software Engineer", "Associate Product Engineer"], 40000),
    ("Thoughtworks", "Consulting", (9.0, 14.0), 2, ["Graduate Consultant Developer"], 35000), ("Amazon", "Product", (25.0, 44.0), 1, ["Software Development Engineer"], 80000),
    ("Microsoft", "Product", (30.0, 48.0), 1, ["Software Engineer"], 90000), ("Bosch Global Software", "Core / Engineering", (6.0, 9.0), 4, ["Software Engineer", "Embedded Developer"], 25000),
    ("Deloitte", "Consulting", (7.0, 11.0), 3, ["Analyst", "Technology Consultant"], 30000), ("Kaar Technologies", "IT Services", (4.0, 5.5), 5, ["Associate Engineer"], 12000),
    ("Mu Sigma", "Consulting", (5.0, 7.0), 3, ["Decision Scientist Trainee"], 18000), ("Sutherland", "IT Services", (3.5, 5.0), 3, ["Associate Analyst"], 12000),
]
LOCATIONS = ["Chennai", "Bengaluru", "Hyderabad", "Coimbatore", "Pune", "Kochi", "Remote"]
OPT_OUT_REASONS = ["Higher studies", "Higher studies", "Entrepreneurship", "Government exam preparation", "Family business"]
ROUND_DETAILS = ["Online aptitude test, coding round, technical interview, HR", "Written test, group discussion, technical interview, HR", "Online coding test, two technical interviews, managerial round",
                 "Aptitude and verbal test, technical interview, HR discussion", "Two coding rounds, system design discussion, HR"]
QUESTIONS = ["Explain the difference between a process and a thread; reverse a linked list; SQL joins on two tables", "Two-sum and sliding window problems; explain REST vs GraphQL; project walkthrough",
             "Normalisation with an example; detect a cycle in a graph; what happens when you type a URL in the browser", "OOP principles with real examples; write a query for the second highest salary; stack vs heap",
             "Binary search variations; indexing in databases; explain your final-year project architecture"]
INTERVIEW_TEXT = ["The panel was friendly and mostly asked about my projects. Be ready to explain every line of your resume.", "Aptitude was the toughest part; the technical round was fundamentals-heavy and conversational.",
                  "They gave a small coding problem and cared more about my approach than the final answer.", "Two technical rounds back to back; the second one went deep into DBMS and operating systems.",
                  "HR round was relaxed. They asked about relocation, shifts and why I chose this company."]
TIPS = ["Revise core subjects (DBMS, OS, networks) and practise easy-to-medium coding problems daily.", "Prepare a two-minute introduction and know your projects thoroughly.",
        "Do mock aptitude tests; speed matters more than you think.", "Be honest when you do not know something, and think aloud when solving problems.", "Keep your GitHub tidy; interviewers do open it."]
DIFFICULTY = ["Easy", "Medium", "Medium", "Medium", "Hard"]
INTERN_ROLES = ["Software Engineering Intern", "Backend Developer Intern", "Data Analyst Intern", "QA Automation Intern", "Cloud Support Intern", "Full-Stack Developer Intern"]
TECH = ["Java, Spring Boot, MySQL", "Python, Django, PostgreSQL", "React, Node.js, MongoDB", "Python, Pandas, Power BI", "Selenium, TestNG, Jenkins", "AWS, Docker, Terraform"]
INTERN_WORK = ["Built and tested REST APIs for an internal tool.", "Automated regression tests and cut manual testing time.", "Cleaned and analysed customer data to build weekly dashboards.",
               "Migrated a service to containers and wrote the deployment scripts.", "Developed UI components and fixed production bugs under a mentor."]
INTERN_LEARN = ["Code reviews, writing testable code and working in an agile team.", "How production systems are monitored, and how to debug under pressure.",
                "Communicating with non-technical stakeholders and estimating work.", "Version control discipline and clean commit history."]
INTERN_TEXT = ["A great learning experience with supportive mentors; I was given real tasks from week one.", "Hybrid mode worked well. The team trusted interns with real work.",
               "Challenging but rewarding. The conversion to a full-time offer depended on the final review."]

HOD_MESSAGE = ("Dear readers, it gives me great pleasure to present this edition of IT Chronicles. This semester our students and faculty have shown what a "
               "curious, collaborative department can achieve: national-level hackathon wins, indexed publications, patents filed and industry partnerships signed. "
               "I thank every contributor, and I invite you to read on.")
VISION = ["To be a centre of excellence in information technology education and research.", "To produce graduates who lead with skill and integrity.",
          "To build lasting partnerships with industry and society.", "To nurture innovation and entrepreneurship among students.", "To advance knowledge through impactful research."]
MISSION = ["Deliver a curriculum that stays current with industry and research.", "Provide a learning environment that rewards curiosity and teamwork.",
           "Support faculty and students in publishing and patenting their ideas.", "Engage with industry, alumni and the community regularly.", "Prepare every student for a meaningful career or higher studies."]
