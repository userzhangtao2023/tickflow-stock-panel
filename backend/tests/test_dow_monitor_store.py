import json
from datetime import UTC, datetime

from app.services.dow_monitor_models import DowNotification, DowTimeframeState
from app.services.dow_monitor_store import DowMonitorStore

NOW = datetime(2026, 7, 23, 9, 30, tzinfo=UTC)


def notification(
    *,
    event_key: str = "01347.HK|30m|OPEN_LONG|LINE-7|1",
    price: float = 1.23,
) -> DowNotification:
    return DowNotification(
        notification_id="notice-1",
        event_key=event_key,
        symbol="01347.HK",
        market="hk",
        timeframe="30m",
        side="BUY",
        action_name="OPEN_LONG",
        shape_name="LINE-7",
        triggered_at=NOW,
        trigger_price=price,
        snapshot_payload={"bar_start": "2026-07-23T09:30:00+00:00"},
    )


def test_store_persists_switches_timeframe_state_and_immutable_notifications(tmp_path):
    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", enabled=True)
    state = DowTimeframeState(
        symbol="01347.HK",
        market="hk",
        timeframe="30m",
        freshness_state="LIVE",
        source_timestamp=NOW,
        snapshot={"signal": "BUY"},
        chart={"series": []},
        updated_at=NOW,
    )
    store.save_state(state)
    first = notification()

    assert store.append_notification(first) is True
    changed = {**first.model_dump(), "trigger_price": 9.99}
    assert store.append_notification(DowNotification.model_validate(changed)) is False

    restored = DowMonitorStore(tmp_path)
    assert restored.list_symbols()[0].enabled is True
    assert restored.get_state("01347.HK", "30m") == state
    assert restored.list_notifications()[0].trigger_price == 1.23


def test_store_replaces_json_files_atomically(tmp_path):
    store = DowMonitorStore(tmp_path)
    storage_dir = tmp_path / "user_data"
    storage_dir.mkdir()
    symbols_path = storage_dir / "dow_monitor_symbols.json"
    symbols_path.write_text('[{"symbol": "OLD.HK"}]', encoding="utf-8")

    store.upsert_symbol("01347.HK", "hk", enabled=True)

    assert json.loads(symbols_path.read_text(encoding="utf-8"))[0]["symbol"] == "01347.HK"
    assert list(storage_dir.glob("dow_monitor_symbols.json.*")) == []


def test_store_ignores_malformed_trailing_jsonl_and_persists_read_status(tmp_path):
    store = DowMonitorStore(tmp_path)
    first = notification()
    assert store.append_notification(first) is True
    notifications_path = tmp_path / "user_data" / "dow_monitor_notifications.jsonl"
    with notifications_path.open("a", encoding="utf-8") as handle:
        handle.write('{"truncated":\n')

    restored = DowMonitorStore(tmp_path)
    assert restored.list_notifications(unread_only=True) == [first]
    assert restored.mark_read(first.notification_id) is True
    assert restored.mark_read("missing") is False

    reread = DowMonitorStore(tmp_path).list_notifications()
    assert reread[0].read_at is not None
    assert DowMonitorStore(tmp_path).list_notifications(unread_only=True) == []


def test_store_recovers_unterminated_jsonl_tail_before_appending_notifications(tmp_path):
    store = DowMonitorStore(tmp_path)
    first = notification()
    assert store.append_notification(first) is True
    notifications_path = tmp_path / "user_data" / "dow_monitor_notifications.jsonl"
    with notifications_path.open("a", encoding="utf-8") as handle:
        handle.write('{"truncated":')

    second = notification(
        event_key="01347.HK|30m|OPEN_LONG|LINE-8|2",
        price=2.34,
    ).model_copy(update={"notification_id": "notice-2"})
    assert store.append_notification(second) is True
    assert store.mark_read(second.notification_id) is True

    restored = DowMonitorStore(tmp_path)
    notifications = {item.notification_id: item for item in restored.list_notifications()}
    assert notifications[first.notification_id].trigger_price == first.trigger_price
    assert notifications[second.notification_id].read_at is not None


def test_store_ignores_non_object_jsonl_records(tmp_path):
    notifications_path = tmp_path / "user_data" / "dow_monitor_notifications.jsonl"
    notifications_path.parent.mkdir()
    notifications_path.write_text("[]\n", encoding="utf-8")

    assert DowMonitorStore(tmp_path).list_notifications() == []


def test_store_deduplicates_notifications_across_existing_store_instances(tmp_path):
    first_store = DowMonitorStore(tmp_path)
    second_store = DowMonitorStore(tmp_path)

    assert first_store.append_notification(notification()) is True
    assert second_store.append_notification(notification()) is False


def test_removing_symbol_keeps_its_historical_notifications(tmp_path):
    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", enabled=True)
    store.save_state(
        DowTimeframeState(
            symbol="01347.HK",
            market="hk",
            timeframe="30m",
            freshness_state="LIVE",
            source_timestamp=NOW,
            snapshot={},
            chart={},
            updated_at=NOW,
        )
    )
    store.append_notification(notification())

    assert store.remove_symbol("01347.HK") is True
    assert store.list_symbols() == []
    assert store.get_state("01347.HK", "30m") is None
    assert store.list_notifications() == [notification()]


def test_store_retrieves_exact_notification_outside_list_limit(tmp_path):
    store = DowMonitorStore(tmp_path)
    first = notification()
    assert store.append_notification(first) is True
    for index in range(1, 1_001):
        assert store.append_notification(
            notification(event_key=f"event-{index}").model_copy(
                update={
                    "notification_id": f"notice-{index}",
                    "triggered_at": NOW.replace(minute=index % 60),
                }
            )
        )

    assert store.get_notification(first.notification_id) == first
