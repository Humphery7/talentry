from talentry_crawler.config import load_label_dictionaries
from talentry_crawler.labeling import Labeler
from talentry_crawler.models import Job, LabelDictionaries

# A tiny dictionary, so each test shows exactly which rule it is checking.
SMALL = LabelDictionaries(
    seniority={"entry": ["Junior"], "senior": ["Senior", "Sr"], "staff": ["Staff"]},  # junior -> senior
    occupations={
        "software-engineer": ["Software Engineer", "Developer"],
        "frontend-developer": ["Frontend Developer"],
        "product-manager": ["Product Manager", "PM"],
    },
    technologies={"python": ["Python"], "java": ["Java"], "react": ["React", "React.js"]},
    case_sensitive_technologies={"java"},
)


def labeled(title: str, description: str = "") -> Job:
    job = Job(url="https://x", title=title, description=description)
    Labeler(SMALL).label(job)
    return job


def test_seniority_comes_from_the_title_only():
    assert labeled("Sr. Software Engineer").seniority == "senior"
    assert labeled("Software Engineer", "We want a senior person").seniority is None


def test_most_senior_word_wins():
    assert labeled("Senior Staff Engineer").seniority == "staff"


def test_longest_occupation_phrase_wins():
    assert labeled("Frontend Developer").occupation == "frontend-developer"
    assert labeled("Backend Developer").occupation == "software-engineer"


def test_acronyms_match_exact_case_only():
    assert labeled("Growth PM").occupation == "product-manager"
    assert labeled("Pm shift cleaner").occupation is None


def test_whole_words_only():
    assert labeled("Seniority Coordinator").seniority is None


def test_technologies_found_in_description_text_not_html_tags():
    job = labeled("Engineer", "<p>You will write <b>Python</b> and React.js</p>")
    assert job.technologies == ["python", "react"]


def test_case_sensitive_technology():
    assert labeled("Engineer", "We use Java daily").technologies == ["java"]
    assert labeled("Engineer", "we love java the island").technologies == []


def test_technology_must_stand_alone():
    assert labeled("Engineer", "Pythonic style").technologies == []


# ---- with the real CSVs -------------------------------------------------------

REAL = Labeler(load_label_dictionaries())


def real(title: str) -> Job:
    job = Job(url="https://x", title=title)
    REAL.label(job)
    return job


def test_real_dictionaries_account_executive_is_not_an_executive():
    job = real("Account Executive, DACH")
    assert job.occupation == "account-executive"
    assert job.seniority is None


def test_real_dictionaries_ceo_is_executive():
    assert real("CEO").seniority == "executive"


def test_real_dictionaries_business_development_manager_is_not_engineering():
    assert real("Business Development Manager").occupation != "engineering-manager"
