from fastapi.testclient import TestClient


def test_day_overview_returns_mocked_data(client: TestClient) -> None:
    response = client.get("/me/day")
    assert response.status_code == 200
    data = response.json()
    assert "date" in data
    assert isinstance(data["calendar"], list)
    assert isinstance(data["tasks"], list)
    assert isinstance(data["emails"], list)
    assert len(data["calendar"]) > 0
    assert len(data["tasks"]) > 0
    assert len(data["emails"]) > 0


def test_day_overview_calendar_event_structure(client: TestClient) -> None:
    response = client.get("/me/day")
    event = response.json()["calendar"][0]
    assert "title" in event
    assert "start" in event
    assert "end" in event


def test_day_overview_task_structure(client: TestClient) -> None:
    response = client.get("/me/day")
    task = response.json()["tasks"][0]
    assert "title" in task
    assert "status" in task


def test_day_overview_email_structure(client: TestClient) -> None:
    response = client.get("/me/day")
    email = response.json()["emails"][0]
    assert "subject" in email
    assert "sender" in email
    assert "priority" in email
