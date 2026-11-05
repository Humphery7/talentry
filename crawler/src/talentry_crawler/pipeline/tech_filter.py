"""Keep only tech / data / engineering jobs.

The labeler assigns an occupation from the title, but plenty of real tech
titles are not in the occupation list ("SDE", "Member of Technical Staff",
"Forward Deployed Engineer", ...).  So this filter uses three signals:

  1. an occupation whitelist,
  2. strong tech title phrases,
  3. a role word (engineer, developer, analyst, ...) plus a tech term or a
     technology detected by the labeler.

Non-tech title phrases (sales, product, finance, mechanical engineering, ...)
are checked first so "Sales Engineer" or "Product Manager - AI" do not slip
through because of a tech word.  A few known-technical exceptions (technical
program manager, information security officer, CTO, ...) are checked before
the non-tech rules.
"""

from __future__ import annotations

import re

from talentry_crawler.models import Job

TECH_OCCUPATIONS = frozenset(
    {
        # software-engineering
        "software-engineer",
        "frontend-developer",
        "backend-developer",
        "fullstack-developer",
        "mobile-developer",
        "embedded-engineer",
        "game-developer",
        "ai-engineer",
        "research-engineer",
        "devops-engineer",
        "release-engineer",
        "qa-engineer",
        "site-reliability-engineer",
        "platform-engineer",
        "cloud-engineer",
        "firmware-engineer",
        "hardware-engineer",
        "asic-engineer",
        "sdet",
        "robotics-engineer",
        "performance-engineer",
        "product-engineer",
        # data-ai
        "data-engineer",
        "data-scientist",
        "ml-engineer",
        "data-analyst",
        "data-annotator",
        "analytics-engineer",
        "mlops-engineer",
        "computer-vision-engineer",
        "nlp-engineer",
        "data-architect",
        "research-scientist",
        "applied-scientist",
        "quantitative-analyst",
        "bioinformatician",
        "geospatial-analyst",
        # infrastructure-security
        "security-engineer",
        "solutions-architect",
        "database-administrator",
        "network-engineer",
        "systems-administrator",
        "application-security-engineer",
        "cloud-architect",
        "cybersecurity-analyst",
        # supporting technical roles
        "technical-writer",
        "engineering-manager",
        "technical-program-manager",
        "tech-lead",
        "customer-engineer",
        "support-engineer",
        "developer-advocate",
    }
)


def _normalise(text: str | None) -> str:
    """Lowercase and turn punctuation into spaces while keeping +, # and . in names."""
    return " ".join(re.findall(r"[a-z0-9+#.]+", (text or "").lower()))


# Checked before the non-tech rules.  These titles contain a phrase that would
# otherwise be rejected (program manager, project manager, security officer).
_TECH_EXCEPTIONS = re.compile(
    "|".join(
        (
            r"\btechnical (?:program|project) manager\b",
            r"\bengineering (?:program|project) manager\b",
            r"\bit (?:program|project) manager\b",
            r"\binformation security officer\b",
            r"\bchief (?:technology|technical|information|information security|data|digital|ai) officer\b",
            r"\b(?:cto|cio|ciso)\b",
            r"\b(?:head|director|vp|vice president|chief)\s+(?:of\s+)?"
            r"(?:engineering|technology|software|data|platform|infrastructure|cloud|"
            r"information security|cybersecurity)\b",
            r"\b(?:engineering|security|network|it|cloud|platform|infrastructure|data)\s+"
            r"operations\s+(?:manager|specialist|coordinator|associate|analyst|engineer|lead|director|vp|head)\b",
            r"\b(?:security|it|information security)\s+auditor\b",
            r"\bcustomer success engineer\b",
        )
    )
)

# Clear non-tech titles.  Keep these specific: a broad word such as "finance"
# would also throw out "Finance Data Analyst", which is a data job.
_NON_TECH_TITLE = re.compile(
    "|".join(
        (
            r"\bsales\s+(?:engineer|engineering|manager|representative|executive|"
            r"specialist|consultant|director|lead|associate|intern)\b",
            r"\bsales development\s+(?:manager|specialist|representative|executive|"
            r"associate|director|lead)\b",
            r"\b(?:head|director|vp|vice president)\s+(?:of\s+)?sales\b",
            r"\b(?:vp|vice president)\s+sales\b",
            r"\baccount\s+(?:executive|manager|director|strategist)\b",
            r"\bbusiness development\s+(?:manager|specialist|representative|executive|"
            r"associate|director|lead|officer)\b",
            r"\bbusiness developer\b",
            r"\breal estate developer\b",
            r"\bmarketing\s+(?:manager|specialist|coordinator|analyst|consultant|director|lead|associate|intern)\b",
            r"\bmarketing operations\b",
            r"\b(?:head|director|vp|vice president)\s+(?:of\s+)?marketing\b",
            r"\bcontent strategist\b",
            r"\bcontent manager\b",
            r"\brecruiter\b",
            r"\brecruiting\s+(?:manager|specialist|coordinator|lead|partner|director)\b",
            r"\brecruitment\s+(?:manager|specialist|coordinator|lead|partner|director)\b",
            r"\btalent acquisition\s+(?:manager|specialist|coordinator|lead|partner|director|recruiter)\b",
            r"\btalent manager\b",
            r"\btalent development\s+(?:manager|specialist|coordinator|lead|director)\b",
            r"\bhuman resources\s+(?:manager|specialist|business partner|coordinator|"
            r"administrator|director|generalist)\b",
            r"\bhr\s+(?:manager|specialist|business partner|administrator|coordinator)\b",
            r"\bpeople operations\s+(?:manager|specialist|coordinator|associate|analyst|"
            r"director|lead)\b",
            r"\bhr operations\s+(?:manager|specialist|coordinator|associate|analyst|"
            r"director|lead)\b",
            r"\bcustomer success\s+(?:manager|specialist|associate|director|lead)\b",
            r"\bcustomer support\s+(?:manager|specialist|associate|representative)\b",
            r"\bproduct\s+(?:manager|owner|director|lead)\b",
            r"\b(?:head|director|vp|vice president)\s+(?:of\s+)?product\b",
            r"\bproject manager\b",
            r"\bprogram manager\b",
            r"\bscrum master\b",
            r"\bagile coach\b",
            r"\bbusiness analyst\b",
            r"\bfinancial analyst\b",
            r"\bfinancial consultant\b",
            r"\bfinancial manager\b",
            r"\bfinance\s+(?:manager|director|analyst|specialist|consultant|lead|operations|controller)\b",
            r"\baccountant\b",
            r"\baccounting\s+(?:manager|specialist|analyst)\b",
            r"\bauditor\b",
            r"\btax\s+(?:advisor|manager|specialist|analyst)\b",
            r"\bpayroll\s+(?:manager|specialist|administrator|coordinator|analyst|clerk)\b",
            r"\blegal\s+(?:counsel|advisor|consultant|manager|specialist)\b",
            r"\blawyer\b",
            r"\battorney\b",
            r"\bparalegal\b",
            r"\bcompliance\s+(?:officer|specialist|manager|analyst|director)\b",
            r"\brisk\s+(?:manager|specialist|analyst|director)\b",
            r"\bexecutive assistant\b",
            r"\badministrative assistant\b",
            r"\boffice manager\b",
            r"\breceptionist\b",
            r"\bsupply chain\s+(?:manager|specialist|analyst|planner|coordinator|director|lead)\b",
            r"\bfacilities\s+(?:manager|specialist|coordinator|director)\b",
            r"\bwarehouse\s+(?:associate|manager|worker|supervisor|specialist)\b",
            r"\bloss prevention\s+(?:specialist|manager|associate|officer)\b",
            r"\bmaintenance\s+(?:technician|engineer|manager|specialist)\b",
            r"\behs specialist\b",
            r"\bconstruction\s+(?:manager|engineer|engineering)\b",
            r"\bquality\s+(?:manager|assurance manager|specialist|associate)\b",
            r"\bpharmacist\b",
            r"\bmedical representative\b",
            r"\bnurse\b",
            r"\bphysician\b",
            r"\bsecurity\s+(?:guard|officer)\b",
            r"\bphysical security\s+(?:manager|specialist|officer|guard|director|consultant)\b",
            r"\blandscape architect\b",
            r"\bbuilding architect\b",
            r"\b(?:mechanical|electrical|civil|chemical|industrial|manufacturing|process|"
            r"biomedical|aerospace|field service|validation|construction|structural|"
            r"environmental|petroleum|mining|agricultural|marine|automotive)\s+"
            r"(?:engineer|engineering)\b",
            r"\bdata entry\b",
            r"\bdata center\s+(?:technician|manager|specialist|associate|analyst|coordinator)\b",
            r"\bnetwork\s+(?:install|installation|technician|cabling)\b",
            r"\bnetwork marketing\b",
            r"\bcnc\s+(?:programmer|operator|machinist)\b",
            r"\bmachinist\b",
            r"\bpre\s?sales\b",
            r"\bgo to market\b",
            r"\boperations\s+(?:manager|specialist|coordinator|associate|analyst)\b",
            r"\b(?:revenue|sales|marketing|business|people|hr|finance|talent|customer)\s+"
            r"operations\s+(?:manager|specialist|coordinator|associate|analyst|director|"
            r"lead|vp|head|partner)\b",
        )
    )
)

# Strong tech titles: these are technical even without a technology keyword.
_STRONG_TECH_TITLE = re.compile(
    "|".join(
        (
            # software / web / mobile role + level
            r"\b(?:software|web|mobile|ios|android|frontend|front end|backend|back end|full ?stack)\s+"
            r"(?:engineer|engineering|developer|development|architect|programmer|scientist|"
            r"analyst|specialist|tester|administrator|consultant)\b",
            # data / AI role + level
            r"\b(?:data|analytics|machine learning|ml|ai|artificial intelligence|llm|genai|"
            r"generative ai|nlp|computer vision|deep learning|mlops|dataops|data science)\s+"
            r"(?:engineer|engineering|developer|scientist|analyst|architect|specialist|"
            r"researcher|lead|manager|director)\b",
            # infrastructure / security / QA role + level
            r"\b(?:devops|devsecops|secops|sre|site reliability|platform|infrastructure|cloud|"
            r"database|network|systems|security|cyber|cybersecurity|appsec|qa|quality assurance|"
            r"sdet|embedded|firmware|hardware|asic|fpga|robotics|mechatronics|release|"
            r"performance|reliability|observability|integration|implementation|deployment|"
            r"build|configuration)\s+"
            r"(?:engineer|engineering|developer|architect|administrator|analyst|specialist|"
            r"tester|scientist)\b",
            # well-known technical titles that do not follow the pattern above
            r"\b(?:member of technical staff|technical staff|tech lead|engineering manager|"
            r"engineering lead|engineering director|engineering program manager|"
            r"technical program manager|technical project manager|developer advocate|"
            r"technical writer|forward deployed engineer)\b",
            # technical management
            r"\b(?:engineering|technology|software|data|platform|infrastructure|cloud|security|"
            r"network|systems|database|qa|devops)\s+"
            r"(?:manager|lead|director|vp|vice president|head)\b",
            r"\b(?:head|director|vp|vice president)\s+(?:of\s+)?"
            r"(?:engineering|technology|software|data|platform|infrastructure|cloud|security|"
            r"information security|cybersecurity)\b",
            r"\b(?:it|information technology)\s+"
            r"(?:manager|director|lead|support|specialist|analyst|administrator|engineer)\b",
            r"\b(?:information security|cybersecurity|application security|network security|"
            r"cloud security|data security)\s+"
            r"(?:manager|director|lead|analyst|engineer|architect|consultant|specialist)\b",
            # BI and vendor/product-specific roles
            r"\b(?:business intelligence|bi)\s+"
            r"(?:developer|analyst|engineer|architect|specialist)\b",
            r"\b(?:salesforce|sap|sas|spss|stata|servicenow|workday|rpa|etl|elt|sql|python|java|javascript|go|golang|"
            r"typescript|react|angular|vue|node|django|flask|spring|dotnet|aws|azure|gcp|docker|"
            r"kubernetes|terraform|ansible|jenkins|pytorch|tensorflow|spark|hadoop|kafka|"
            r"airflow|dbt|snowflake|databricks|tableau|power bi|looker|qlik|sharepoint|jira)\s+"
            r"(?:developer|engineer|architect|administrator|analyst|scientist|specialist|"
            r"consultant|manager)\b",
            # common acronyms
            r"\b(?:sde|swe|sdet|qa|tpm|cto|cio|ciso|ml|ai|llm|genai|nlp|mlops|devops|sre)\b",
            # build / release / test / solution roles
            r"\bproduction\s+(?:engineer|engineering|developer|architect|analyst|specialist|consultant)\b",
            r"\b(?:build|configuration|deployment|implementation|integration)\s+"
            r"(?:engineer|engineering|developer|architect|analyst|specialist|consultant|"
            r"lead|manager)\b",
            r"\btest\s+(?:engineer|engineering|analyst|automation|specialist|lead|manager|"
            r"tester|technician)\b",
            r"\bqa automation\s+(?:engineer|specialist|lead|manager|tester)\b",
            r"\btest automation\s+(?:engineer|specialist|lead|manager|tester)\b",
            r"\bsolutions\s+(?:engineer|engineering|architect|consultant|specialist|manager|lead)\b",
            r"\benterprise architect\b",
            # IT support
            r"\b(?:help desk|desktop support|technical support|it support|production support)\s+"
            r"(?:engineer|analyst|specialist|technician|administrator|representative)\b",
            r"\bsupport engineer\b",
            r"\b(?:soc|noc|security operations center|network operations center)\s+"
            r"(?:analyst|engineer|specialist|technician|manager|lead)\b",
            r"\b(?:penetration tester|pen tester)\b",
            r"\b(?:incident response|threat intelligence|malware|digital forensics)\s+"
            r"(?:analyst|engineer|specialist|researcher)\b",
            # computing / data-science field titles
            r"\b(?:computer|mainframe|cobol)\s+"
            r"(?:scientist|programmer|engineer|analyst|developer)\b",
            r"\b(?:statistician|biostatistician)\b",
            r"\b(?:data science|machine learning|artificial intelligence|deep learning)\b",
            r"\b(?:game|application|applications)\s+"
            r"(?:developer|programmer|engineer|architect|tester)\b",
        )
    )
)

# A title that has a role word and at least one of these is technical too.
# This catches long, messy titles such as
# "Senior Python/Flask + React Fullstack Engineer - Remote".
_TECH_TERM = re.compile(
    "|".join(
        (
            r"\bsoftware\b",
            r"\bweb\b",
            r"\bmobile\b",
            r"\bios\b",
            r"\bandroid\b",
            r"\bfrontend\b",
            r"\bfront end\b",
            r"\bbackend\b",
            r"\bback end\b",
            r"\bfull ?stack\b",
            r"\bdata\b",
            r"\banalytics\b",
            r"\bmachine learning\b",
            r"\bml\b",
            r"\bai\b",
            r"\bartificial intelligence\b",
            r"\bllm\b",
            r"\bgenai\b",
            r"\bgenerative ai\b",
            r"\bnlp\b",
            r"\bcomputer vision\b",
            r"\bdeep learning\b",
            r"\bmlops\b",
            r"\bdataops\b",
            r"\bdevops\b",
            r"\bdevsecops\b",
            r"\bsecops\b",
            r"\bsre\b",
            r"\bsite reliability\b",
            r"\bplatform\b",
            r"\binfrastructure\b",
            r"\bcloud\b",
            r"\bdatabase\b",
            r"\bnetwork\b",
            r"\bsystems\b",
            r"\bsecurity\b",
            r"\bcyber\b",
            r"\bcybersecurity\b",
            r"\bappsec\b",
            r"\bqa\b",
            r"\bquality assurance\b",
            r"\bsdet\b",
            r"\bembedded\b",
            r"\bfirmware\b",
            r"\bhardware\b",
            r"\basic\b",
            r"\bfpga\b",
            r"\brobotics\b",
            r"\bmechatronics\b",
            r"\brelease\b",
            r"\bperformance\b",
            r"\breliability\b",
            r"\bobservability\b",
            r"\bintegration\b",
            r"\bimplementation\b",
            r"\bdeployment\b",
            r"\bbuild\b",
            r"\bconfiguration\b",
            r"\btest\b",
            r"\btechnical\b",
            r"\btechnology\b",
            r"\bcomputer\b",
            r"\bmainframe\b",
            r"\bcobol\b",
            r"\bsql\b",
            r"\bpython\b",
            r"\bjava\b",
            r"\bgo\b",
            r"\bgolang\b",
            r"\bjavascript\b",
            r"\btypescript\b",
            r"\breact\b",
            r"\bangular\b",
            r"\bvue\b",
            r"\bnode\b",
            r"\bnodejs\b",
            r"\bnode\.js\b",
            r"\bdjango\b",
            r"\bflask\b",
            r"\bspring\b",
            r"\bdotnet\b",
            r"\.net\b",
            r"\baws\b",
            r"\bazure\b",
            r"\bgcp\b",
            r"\bdocker\b",
            r"\bkubernetes\b",
            r"\bterraform\b",
            r"\bansible\b",
            r"\bjenkins\b",
            r"\bgit\b",
            r"\bgithub\b",
            r"\bgitlab\b",
            r"\blinux\b",
            r"\bunix\b",
            r"\bwindows\b",
            r"\bserver\b",
            r"\bapi\b",
            r"\bmicroservices\b",
            r"\bsaas\b",
            r"\berp\b",
            r"\bcrm\b",
            r"\bsalesforce\b",
            r"\bsap\b",
            r"\bsas\b",
            r"\bspss\b",
            r"\bstata\b",
            r"\bservicenow\b",
            r"\bworkday\b",
            r"\brpa\b",
            r"\betl\b",
            r"\belt\b",
            r"\bdata warehouse\b",
            r"\bdata lake\b",
            r"\bbig data\b",
            r"\bspark\b",
            r"\bhadoop\b",
            r"\bkafka\b",
            r"\bairflow\b",
            r"\bdbt\b",
            r"\bsnowflake\b",
            r"\bdatabricks\b",
            r"\btableau\b",
            r"\bpower bi\b",
            r"\blooker\b",
            r"\bqlik\b",
            r"\bsharepoint\b",
            r"\bjira\b",
            r"\bconfluence\b",
            r"\bprometheus\b",
            r"\bgrafana\b",
            r"\bdatadog\b",
            r"\bsplunk\b",
            r"\belasticsearch\b",
            r"\bmongodb\b",
            r"\bpostgres\b",
            r"\bpostgresql\b",
            r"\bmysql\b",
            r"\bredis\b",
            r"\bgraphql\b",
            r"\brest\b",
            r"\bgrpc\b",
            r"\bwebsocket\b",
            r"\boauth\b",
            r"\bsaml\b",
            r"\bsso\b",
            r"\bvpn\b",
            r"\bfirewall\b",
            r"\bdns\b",
            r"\btcp\b",
            r"\bhttp\b",
            r"\bhttps\b",
            r"\bssl\b",
            r"\btls\b",
            r"\bit support\b",
            r"\bhelp desk\b",
            r"\bdesktop support\b",
            r"\btechnical support\b",
            r"\bproduction support\b",
            r"\bit\b",
            r"\binformation technology\b",
            r"\bsoc\b",
            r"\bnoc\b",
            r"\bincident response\b",
            r"\bthreat intelligence\b",
            r"\bmalware\b",
            r"\bdigital forensics\b",
            r"\bpenetration testing\b",
            r"\bpentest\b",
            r"\bvulnerability\b",
            r"\bzero trust\b",
            r"\biam\b",
            r"\bidentity\b",
            r"\baccess management\b",
            r"\bcloud security\b",
            r"\bnetwork security\b",
            r"\bapplication security\b",
            r"\binformation security\b",
            r"\bquantitative\b",
            r"\bstatistician\b",
            r"\bgame\b",
            r"\bapplication\b",
            r"\bapplications\b",
        )
    )
)

_ROLE_WORD = re.compile(
    r"\b(?:engineer|engineering|developer|development|programmer|architect|analyst|"
    r"scientist|administrator|specialist|consultant|tester|lead|researcher)\b"
)


def is_tech_job(job: Job) -> bool:
    """True when a labeled job belongs in the tech / data / engineering catalog."""
    if job.occupation in TECH_OCCUPATIONS:
        return True

    title = _normalise(job.title)
    if not title:
        return False
    if _TECH_EXCEPTIONS.search(title):
        return True
    if _NON_TECH_TITLE.search(title):
        return False
    if _STRONG_TECH_TITLE.search(title):
        return True
    return bool(_ROLE_WORD.search(title) and (job.technologies or _TECH_TERM.search(title)))
