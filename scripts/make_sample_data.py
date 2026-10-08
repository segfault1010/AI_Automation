"""Generate realistic sample attendance, marks and timetable CSVs into data/sample/."""
import csv
import random
from pathlib import Path

random.seed(7)
OUT = Path(__file__).resolve().parent.parent / "data" / "sample"
OUT.mkdir(parents=True, exist_ok=True)

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
SLOTS = ["09:00-10:00", "10:00-11:00", "11:15-12:15", "12:15-13:15", "14:00-15:00", "15:00-16:00"]
DEPTS = {
    "CSE": (["Data Structures", "DBMS", "Operating Systems", "Computer Networks"],
            ["Dr. Priya Raman", "Prof. Arjun Mehta", "Dr. Kavitha S", "Prof. Rahul Nair"], "Dr. Meena Iyer"),
    "ECE": (["Signals & Systems", "Digital Electronics", "Microprocessors", "Communication Theory"],
            ["Dr. Suresh Kumar", "Prof. Anitha R", "Dr. Vikram Rao", "Prof. Divya Menon"], "Dr. Ramesh Pillai"),
    "MECH": (["Thermodynamics", "Fluid Mechanics", "Machine Design", "Manufacturing Tech"],
             ["Dr. Ganesh B", "Prof. Lakshmi N", "Dr. Karthik V", "Prof. Sneha Joshi"], "Dr. Anand Krishnan"),
}
FIRST = ["Aarav", "Diya", "Rohan", "Ananya", "Karthik", "Meera", "Vivek", "Ishita", "Arjun", "Sneha",
         "Rahul", "Pooja", "Aditya", "Nivetha", "Siddharth", "Kavya", "Harish", "Shreya", "Varun", "Lavanya",
         "Nikhil", "Divya", "Pranav", "Swathi", "Akash", "Deepika", "Manoj", "Keerthana", "Gokul", "Priyanka"]
LAST = ["Sharma", "Iyer", "Reddy", "Nair", "Menon", "Rao", "Kumar", "Pillai", "Gupta", "Krishnan",
        "Subramanian", "Patel", "Das", "Bose", "Joshi"]


def email_of(name: str) -> str:
    return name.lower().replace("dr. ", "").replace("prof. ", "").replace(" ", ".") + "@example.edu"


att_rows, mark_rows, tt_rows = [], [], []
n = 0
for dept, (subjects, teachers, adviser) in DEPTS.items():
    held_by_subject = {s: random.randint(40, 48) for s in subjects}
    for i in range(14):
        n += 1
        roll = f"23{dept[:2]}{i + 1:03d}"
        name = f"{random.choice(FIRST)} {random.choice(LAST)}"
        profile = random.choices(["good", "near", "low", "very_low"], weights=[6, 3, 3, 1])[0]
        mark_profile = random.choices(["good", "weak", "falling"], weights=[6, 2, 2])[0]
        for s in subjects:
            held = held_by_subject[s]
            base = {"good": random.uniform(0.9, 1.0), "near": random.uniform(0.85, 0.9),
                    "low": random.uniform(0.74, 0.86), "very_low": random.uniform(0.6, 0.75)}[profile]
            attended = min(held, round(held * base))
            att_rows.append({
                "roll_no": roll, "name": name, "email": email_of(name + str(n)),
                "phone": f"+9198{random.randint(10000000, 99999999)}", "department": dept,
                "adviser_name": adviser, "adviser_email": email_of(adviser),
                "subject": s, "classes_held": held, "classes_attended": attended,
            })
            t1 = random.randint(55, 92)
            if mark_profile == "weak" and random.random() < 0.6:
                tests = [random.randint(30, 50), random.randint(25, 45), random.randint(20, 39)]
            elif mark_profile == "falling" and random.random() < 0.6:
                tests = [t1, max(0, t1 - random.randint(5, 12)), max(0, t1 - random.randint(15, 30))]
            else:
                tests = [t1, min(100, t1 + random.randint(-6, 8)), min(100, t1 + random.randint(-6, 10))]
            mark_rows.append({"roll_no": roll, "subject": s, "test1": tests[0], "test2": tests[1], "test3": tests[2]})
    for s, t in zip(subjects, teachers):
        busy = random.sample([(d, sl) for d in DAYS for sl in SLOTS], k=random.randint(14, 18))
        for d, sl in sorted(busy, key=lambda x: (DAYS.index(x[0]), SLOTS.index(x[1]))):
            tt_rows.append({"teacher": t, "teacher_email": email_of(t), "department": dept,
                            "subject": s, "day": d, "slot": sl})


def write(name, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


write("attendance.csv", att_rows)
write("marks.csv", mark_rows)
write("timetable.csv", tt_rows)
print(f"Wrote {len(att_rows)} attendance rows, {len(mark_rows)} mark rows, {len(tt_rows)} timetable rows to {OUT}")
