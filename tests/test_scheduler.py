from app.config import Settings


class FakeScheduler:
    instances = []

    def __init__(self, timezone: str) -> None:
        self.timezone = timezone
        self.jobs = []
        self.started = False
        self.__class__.instances.append(self)

    def add_job(self, func, trigger: str, **kwargs) -> None:
        self.jobs.append((func, trigger, kwargs))

    def start(self) -> None:
        self.started = True


def test_scheduler_does_not_add_high_impact_monitor_by_default(monkeypatch) -> None:
    import app.scheduler as scheduler_module

    FakeScheduler.instances = []
    monkeypatch.setattr(scheduler_module, "BlockingScheduler", FakeScheduler)
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: Settings())
    monkeypatch.setattr(scheduler_module, "init_db", lambda settings: None)

    scheduler_module.start_scheduler()

    scheduler = FakeScheduler.instances[0]
    job_ids = [kwargs["id"] for _, _, kwargs in scheduler.jobs]
    assert job_ids == ["morning_brief", "market_close"]


def test_scheduler_adds_high_impact_monitor_when_enabled(monkeypatch) -> None:
    import app.scheduler as scheduler_module

    FakeScheduler.instances = []
    monkeypatch.setattr(scheduler_module, "BlockingScheduler", FakeScheduler)
    monkeypatch.setattr(
        scheduler_module,
        "get_settings",
        lambda: Settings(alert_monitor_enabled=True),
    )
    monkeypatch.setattr(scheduler_module, "init_db", lambda settings: None)

    scheduler_module.start_scheduler()

    scheduler = FakeScheduler.instances[0]
    job_ids = [kwargs["id"] for _, _, kwargs in scheduler.jobs]
    assert job_ids == ["morning_brief", "market_close", "high_impact_monitor"]
