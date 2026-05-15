import httpx
import structlog

from app.config import settings
from app.parsers.base import ParsedVacancy

log = structlog.get_logger()

HH_API = "https://api.hh.ru"

EXPERIENCE_MAP = {
    "no": "noExperience",
    "1-3": "between1And3",
    "3-6": "between3And6",
    "6+": "moreThan6",
}


class HHParser:
    platform = "hh"

    def __init__(self):
        self.headers = {
            "User-Agent": "job-hunter/1.0 (i.egorov8080@gmail.com)",
        }

    async def login(self) -> bool:
        return True

    async def search_vacancies(self, query: str, **filters) -> list[ParsedVacancy]:
        params = {
            "text": query,
            "per_page": 50,
            "search_field": "name",
            "order_by": "publication_time",
        }

        if filters.get("remote", True):
            params["schedule"] = "remote"

        if filters.get("salary_from"):
            params["salary"] = str(filters["salary_from"])
            params["only_with_salary"] = "true"

        exp = filters.get("experience")
        if exp and exp in EXPERIENCE_MAP:
            params["experience"] = EXPERIENCE_MAP[exp]

        vacancies = []
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
                resp = await client.get(f"{HH_API}/vacancies", params=params)
                resp.raise_for_status()
                data = resp.json()

            for item in data.get("items", []):
                vacancy = self._parse_item(item)
                if vacancy:
                    vacancies.append(vacancy)

            log.info("hh_api_search", query=query, found=len(vacancies))

        except Exception as e:
            log.error("hh_api_search_error", query=query, error=str(e))

        return vacancies

    def _parse_item(self, item: dict) -> ParsedVacancy | None:
        salary_from, salary_to, currency = None, None, ""
        sal = item.get("salary")
        if sal:
            salary_from = sal.get("from")
            salary_to = sal.get("to")
            currency = sal.get("currency", "")

        area = item.get("area", {})
        schedule = item.get("schedule", {})
        is_remote = schedule.get("id") == "remote"

        employer = item.get("employer", {})

        return ParsedVacancy(
            platform="hh",
            external_id=str(item.get("id", "")),
            url=item.get("alternate_url", ""),
            title=item.get("name", ""),
            company_name=employer.get("name", ""),
            company_url=employer.get("alternate_url", ""),
            salary_from=salary_from,
            salary_to=salary_to,
            salary_currency=currency,
            location=area.get("name", ""),
            is_remote=is_remote,
        )

    async def get_vacancy_details(self, url: str) -> ParsedVacancy | None:
        vacancy_id = url.rstrip("/").split("/")[-1].split("?")[0]
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
                resp = await client.get(f"{HH_API}/vacancies/{vacancy_id}")
                resp.raise_for_status()
                data = resp.json()

            skills = [s["name"] for s in data.get("key_skills", [])]
            experience = data.get("experience", {}).get("name", "")
            employment = data.get("employment", {}).get("name", "")

            desc_html = data.get("description", "")
            from html import unescape
            import re
            description = re.sub(r"<[^>]+>", " ", unescape(desc_html))
            description = re.sub(r"\s+", " ", description).strip()

            return ParsedVacancy(
                platform="hh",
                external_id=vacancy_id,
                url=data.get("alternate_url", url),
                title=data.get("name", ""),
                description=description,
                experience=experience,
                employment_type=employment,
                skills=skills,
            )

        except Exception as e:
            log.error("hh_api_details_error", vacancy_id=vacancy_id, error=str(e))
            return None

    async def apply_to_vacancy(self, url: str, cover_letter: str) -> bool:
        log.warning("hh_api_apply_not_supported", url=url, reason="requires OAuth token")
        return False

    async def check_messages(self) -> list[dict]:
        log.info("hh_api_messages_skip", reason="requires OAuth token")
        return []
