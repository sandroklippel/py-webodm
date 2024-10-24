"""
pywebodm
"""

from typing import Iterator
from datetime import datetime, timedelta
from enum import Enum
from urllib.parse import urlparse
from pywebodm.utils import odmpreset_to_dict, fmt_endpoint

import requests


class TaskStatus(Enum):
    """Task status

    QUEUED: Task's files have been uploaded and are waiting to be processed.
    RUNNING: Task is currently being processed.
    FAILED:	Task has failed for some reason (not enough images, out of memory, etc).
    COMPLETED: Task has completed. Assets are be ready to be downloaded.
    CANCELED: Task was manually canceled by the user.
    """

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
    def processing_time(self) -> timedelta | None:
        try:
            return timedelta(milliseconds=self._data.get("processing_time"))
        except (ValueError, TypeError):
            return None

    @property
    def status(self) -> TaskStatus | None:
        try:
            return TaskStatus(self._data.get("status"))
        except (ValueError, TypeError):
            return None

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
    def available_assets(self) -> list:
        return self._data.get("available_assets", [])

    @property
    def tags(self) -> list:
        return self._data.get("tags", [])

    @property
    def date(self) -> datetime | None:

        try:
            return datetime.strptime(
                self._data.get("created_at"), "%Y-%m-%dT%H:%M:%S.%fZ"
            )
        except (ValueError, TypeError):
            return None

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
            return datetime.strptime(
                self._data.get("created_at"), "%Y-%m-%dT%H:%M:%S.%fZ"
            )
        except (ValueError, TypeError):
            return None

    def tasks(self) -> Iterator[int]:
        for task in self._data["tasks"]:
            yield task

    def can_add(self) -> bool:
        return "add" in self._data["permissions"]

    def can_delete(self) -> bool:
        return "delete" in self._data["permissions"]

    def can_change(self) -> bool:
        return "change" in self._data["permissions"]

    def can_view(self) -> bool:
        return "view" in self._data["permissions"]


class WebODM:
    """Main class for communication with the WebODM API"""

    def __init__(self, url, username, password, token_expiration=21600):

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
        self._token_datetime = datetime.now()
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
            self._token_datetime = datetime.now()
        return self._token

    def create_project(self, name, description):
        path = "/api/projects/"
        endpoint = fmt_endpoint(self._scheme, self._netloc, path)
        res = self._session.post(
            endpoint,
            headers=self.headers,
            data={"name": name, "description": description},
        )
        if res.status_code == 201:
            return Project(res.json())

    def list_projects(self, **filters):
        # filters: search=&id=&name=&description=&created_at
        path = "/api/projects/"
        endpoint = fmt_endpoint(self._scheme, self._netloc, path)
        res = self._session.get(endpoint, headers=self.headers, params=filters)
        if res.status_code == 200:
            return [Project(p) for p in res.json()]

    def read_project(self, project_id):
        path = f"/api/projects/{project_id}"
        endpoint = fmt_endpoint(self._scheme, self._netloc, path)
        res = self._session.get(endpoint, headers=self.headers)
        if res.status_code == 200:
            return Project(res.json())

    def delete_project(self, project_id):
        path = f"/api/projects/{project_id}"
        endpoint = fmt_endpoint(self._scheme, self._netloc, path)
        res = self._session.delete(endpoint, headers=self.headers)
        if res.status_code == 204:
            return True
        return False
    
    def list_project_tasks(self, project_id):
        path = f"/api/projects/{project_id}/tasks/"
        endpoint = fmt_endpoint(self._scheme, self._netloc, path)
        res = self._session.get(endpoint, headers=self.headers)
        if res.status_code == 200:
            return [Task(p) for p in res.json()]

    def read_task(self, project_id, task_id):
        path = f"/api/projects/{project_id}/tasks/{task_id}/"
        endpoint = fmt_endpoint(self._scheme, self._netloc, path)
        res = self._session.get(endpoint, headers=self.headers)
        if res.status_code == 200:
            return Task(res.json())
    
    def delete_task(self, project_id, task_id):
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
            datetime.now() - self._token_datetime
        ).total_seconds() < self._token_expiration and self._token:
            return self._token
        return self.token_refresh()

    @property
    def headers(self) -> dict:
        return {"Authorization": "JWT {}".format(self.token)}
