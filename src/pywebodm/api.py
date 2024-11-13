"""
pywebodm

Python library for interacting with the WebODM API.

api.py - Main API classes and functions

"""

from typing import Iterator
from datetime import datetime, timedelta, timezone
from enum import Enum
from urllib.parse import urlparse
from pywebodm.utils import odmpreset_to_dict, fmt_endpoint

import requests


class TaskStatus(Enum):
    """Task status

    UNKNOWN: Some unforeseen situation
    QUEUED: Task's files have been uploaded and are waiting to be processed.
    RUNNING: Task is currently being processed.
    FAILED:	Task has failed for some reason (not enough images, out of memory, etc).
    COMPLETED: Task has completed. Assets are be ready to be downloaded.
    CANCELED: Task was manually canceled by the user.
    """

    UNKNOWN = 0
    QUEUED = 10
    RUNNING = 20
    FAILED = 30
    COMPLETED = 40
    CANCELED = 50


class Task:
    """Class to parse task data from WebODM API"""

    def __init__(self, data: dict) -> None:
        self._data = data

    @property
    def id(self) -> str:
        return self._data["id"]

    @property
    def project(self) -> int:
        return self._data["project"]

    @property
    def processing_node(self) -> int | None:
        return self._data.get("processing_node")

    @property
    def processing_node_name(self) -> str | None:
        return self._data.get("processing_node_name")

    @property
    def images_count(self) -> int | None:
        return self._data.get("images_count")

    @property
    def uuid(self) -> str | None:
        return self._data.get("uuid")

    @property
    def name(self) -> str:
        return self._data.get("name", "")

    @property
    def processing_time(self) -> timedelta:
        try:
            return timedelta(milliseconds=self._data.get("processing_time", 0))
        except (ValueError, TypeError):
            return timedelta(milliseconds=0)

    @property
    def status(self) -> TaskStatus:
        try:
            return TaskStatus(self._data.get("status", 0))
        except (ValueError, TypeError):
            return TaskStatus(0)

    @property
    def last_error(self) -> str:
        return self._data.get("last_error", "")

    @property
    def epsg(self) -> int | None:
        return self._data.get("epsg")

    @property
    def size(self) -> float | None:
        return self._data.get("size")

    @property
    def options(self) -> dict:
        return odmpreset_to_dict(self._data.get("options", {}))

    @property
    def statistics(self) -> dict:
        return self._data.get("statistics", {})

    @property
    def area(self) -> float | None:
        """if available, returns the area in m2"""
        return self.statistics.get("area")

    @property
    def gsd(self) -> float | None:
        """if available, returns the gsd in cm"""
        return self.statistics.get("gsd")

    @property
    def points(self) -> int | None:
        """if available, returns the number of reconstructed points"""
        pc = self.statistics.get("pointcloud", {})
        return pc.get("points")

    @property
    def available_assets(self) -> list:
        return self._data.get("available_assets", [])

    @property
    def tags(self) -> list:
        return self._data.get("tags", [])

    @property
    def date(self) -> datetime | None:

        try:
            return (
                datetime.strptime(
                    self._data.get("created_at"), "%Y-%m-%dT%H:%M:%S.%fZ"  # ISO 8601
                )
            ).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None

    @property
    def age(self) -> timedelta:
        if not self.finished:
            return timedelta(milliseconds=0)
        try:
            return datetime.now(timezone.utc) - (self.date + self.processing_time)
        except (ValueError, TypeError):
            return timedelta(milliseconds=0)

    @property
    def upload_progress(self) -> float:
        return float(self._data.get("upload_progress", 0))

    @property
    def resize_progress(self) -> float:
        return float(self._data.get("resize_progress", 0))

    @property
    def running_progress(self) -> float:
        return float(self._data.get("running_progress", 0))

    @property
    def partial(self) -> bool:
        return self._data.get("partial", False)

    @property
    def finished(self) -> bool:
        return self.status in [
            TaskStatus.CANCELED,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
        ]


class Project:
    """Class to parse project data from WebODM API"""

    def __init__(self, data: dict) -> None:
        self._data = data

    @property
    def id(self) -> int:
        return self._data["id"]

    @property
    def name(self) -> str:
        return self._data["name"]

    @property
    def description(self) -> str | None:
        return self._data.get("description")

    @property
    def date(self) -> datetime | None:

        try:
            return (
                datetime.strptime(self._data.get("created_at"), "%Y-%m-%dT%H:%M:%S.%fZ")
            ).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None

    @property
    def task_list(self) -> list:
        return self._data["tasks"]

    @property
    def task_count(self) -> int:
        return len(self._data["tasks"])

    @property
    def can_add(self) -> bool:
        return "add" in self._data["permissions"]

    @property
    def can_delete(self) -> bool:
        return "delete" in self._data["permissions"]

    @property
    def can_change(self) -> bool:
        return "change" in self._data["permissions"]

    @property
    def can_view(self) -> bool:
        return "view" in self._data["permissions"]

    def tasks(self) -> Iterator[str]:
        for task in self._data["tasks"]:
            yield task


class WebODM:
    """Main class for communication with the WebODM API"""

    def __init__(
        self, url: str, username: str, password: str, token_expiration: int = 21600
    ) -> None:

        url_parsed = urlparse(url)
        if url_parsed.scheme not in ("http", "https"):
            raise ValueError("Invalid URL")
        if not url_parsed.hostname:
            raise ValueError("Invalid URL")
        _ = url_parsed.port  # check ports range

        self._scheme = url_parsed.scheme
        self._netloc = url_parsed.netloc
        self._username = username
        self._password = password
        self._token = ""
        self._token_expiration = token_expiration
        self._token_datetime = datetime.now(timezone.utc)
        self._session = requests.Session()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self) -> None:
        self._session.close()
        self._session = None

    def token_refresh(self) -> str:
        path = "/api/token-auth/"
        endpoint = fmt_endpoint(self._scheme, self._netloc, path)
        res = self._session.post(
            endpoint, data={"username": self._username, "password": self._password}
        )
        if res.status_code == 200:
            self._token = res.json()["token"]
            self._token_datetime = datetime.now(timezone.utc)
        return self._token

    def create_project(self, name: str, description: str) -> Project:
        path = "/api/projects/"
        endpoint = fmt_endpoint(self._scheme, self._netloc, path)
        res = self._session.post(
            endpoint,
            headers=self.headers,
            data={"name": name, "description": description},
        )
        if res.status_code == 201:
            return Project(res.json())

    def list_projects(self, **filters) -> list:
        # filters: search=&id=&name=&description=&created_at
        path = "/api/projects/"
        endpoint = fmt_endpoint(self._scheme, self._netloc, path)
        res = self._session.get(endpoint, headers=self.headers, params=filters)
        if res.status_code == 200:
            return [Project(p) for p in res.json()]

    def read_project(self, project_id: int) -> Project:
        path = f"/api/projects/{project_id}"
        endpoint = fmt_endpoint(self._scheme, self._netloc, path)
        res = self._session.get(endpoint, headers=self.headers)
        if res.status_code == 200:
            return Project(res.json())

    def delete_project(self, project_id: int) -> bool:
        path = f"/api/projects/{project_id}"
        endpoint = fmt_endpoint(self._scheme, self._netloc, path)
        res = self._session.delete(endpoint, headers=self.headers)
        if res.status_code == 204:
            return True
        return False

    def list_project_tasks(self, project_id: int) -> list:
        path = f"/api/projects/{project_id}/tasks/"
        endpoint = fmt_endpoint(self._scheme, self._netloc, path)
        res = self._session.get(endpoint, headers=self.headers)
        if res.status_code == 200:
            return [Task(p) for p in res.json()]

    def read_task(self, project_id: int, task_id: str) -> Task:
        path = f"/api/projects/{project_id}/tasks/{task_id}/"
        endpoint = fmt_endpoint(self._scheme, self._netloc, path)
        res = self._session.get(endpoint, headers=self.headers)
        if res.status_code == 200:
            return Task(res.json())

    def delete_task(self, project_id: int, task_id: str) -> bool:
        path = f"/api/projects/{project_id}/tasks/{task_id}/remove/"
        endpoint = fmt_endpoint(self._scheme, self._netloc, path)
        res = self._session.post(endpoint, headers=self.headers)
        if res.status_code == 200:
            return res.json()["success"]
        return False

    @property
    def closed(self) -> bool:
        return self._session is None

    @property
    def token(self) -> str:
        if (
            datetime.now(timezone.utc) - self._token_datetime
        ).total_seconds() < self._token_expiration and self._token:
            return self._token
        return self.token_refresh()

    @property
    def headers(self) -> dict:
        return {"Authorization": "JWT {}".format(self.token)}
