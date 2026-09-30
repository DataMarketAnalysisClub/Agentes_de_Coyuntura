from app.config import Settings
from app.main import run_subscribers_command
from services.subscriptions import SubscriptionService
from storage.subscribers import SubscriberStatus


def test_subscribers_cli_add_count_list_remove_erase(subscriber_repository, capsys) -> None:
    service = SubscriptionService(subscriber_repository, Settings(mailing_public_url="https://x.ts.net"))

    assert run_subscribers_command(["add", "DMAC@udd.cl"], service) == 0
    assert run_subscribers_command(["add", "no-es-correo"], service) == 2
    assert run_subscribers_command(["count"], service) == 0
    assert run_subscribers_command(["list", "active"], service) == 0
    output = capsys.readouterr().out
    assert "Activo: dmac@udd.cl" in output
    assert "active        1" in output
    assert "dmac@udd.cl\tactive\tadmin" in output

    assert run_subscribers_command(["remove", "dmac@udd.cl"], service) == 0
    assert subscriber_repository.get_by_email("dmac@udd.cl").status is SubscriberStatus.UNSUBSCRIBED
    assert run_subscribers_command(["erase", "dmac@udd.cl"], service) == 0
    assert run_subscribers_command(["erase", "dmac@udd.cl"], service) == 1
    assert run_subscribers_command(["list", "raro"], service) == 2
    assert run_subscribers_command(["borrar"], service) == 2
