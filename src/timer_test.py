import timer
import datetime as dt

def datetime(*args):
    return dt.datetime(*args, tzinfo=dt.UTC)

def test_periodic_timer():
    controller = timer.PeriodicWakeupController(datetime(2024, 1, 1, 10, 11, 12), dt.timedelta(days=1))
    assert controller.next_wakeup(datetime(2024, 1, 1, 10, 11, 12)) == datetime(2024, 1, 2, 10, 11, 12)

    assert controller.next_wakeup(datetime(2025, 12, 12, 4, 0, 0)) == datetime(2025, 12, 12, 10, 11, 12)
    assert controller.next_wakeup(datetime(2025, 12, 12, 14, 0, 0)) == datetime(2025, 12, 13, 10, 11, 12)

    controller = timer.PeriodicWakeupController(datetime(2024, 1, 1, 10, 11, 12), dt.timedelta(hours=1))
    assert controller.next_wakeup(datetime(2025, 12, 12, 4, 0, 0)) == datetime(2025, 12, 12, 4, 11, 12)
    assert controller.next_wakeup(datetime(2025, 12, 12, 14, 0, 0)) == datetime(2025, 12, 12, 14, 11, 12)

    controller = timer.PeriodicWakeupController(datetime(2024, 1, 1, 10, 11, 12), dt.timedelta(minutes=24))
    assert controller.next_wakeup(datetime(2024, 1, 1, 10, 11, 12)) == datetime(2024, 1, 1, 10, 35, 12)
    assert controller.next_wakeup(datetime(2024, 1, 1, 10, 11, 12, 100)) == datetime(2024, 1, 1, 10, 35, 12)
    assert controller.next_wakeup(datetime(2025, 12, 12, 4, 0, 0)) == datetime(2025, 12, 12, 4, 11, 12)
    assert controller.next_wakeup(datetime(2025, 12, 12, 14, 0, 0)) == datetime(2025, 12, 12, 14, 11, 12)
    assert controller.next_wakeup(datetime(2025, 12, 12, 15, 0, 0)) == datetime(2025, 12, 12, 15, 23, 12)