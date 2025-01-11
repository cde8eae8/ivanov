import threading
import typing
import datetime as dt
import time

class TimerThread:
    def __init__(self, get_next_wakeup_time: typing.Callable[[], dt.datetime], callback: typing.Callable[[], None]):
        self._get_next_wakeup_time = get_next_wakeup_time
        self._callback = callback
        self._thread = None
        self._exited = threading.Event()
        self._exited.clear()

    def start(self):
        assert not self._exited.is_set()
        self._thread = threading.Thread(target=self._do_start, name="Timer")
        self._thread.start()

    def stop(self):
        self._exited.set()
        self._thread.join()

    def python_thread(self):
        return self._thread

    def _do_start(self):
        now = dt.datetime.now(dt.UTC)
        self._next_wakeup = self._get_next_wakeup_time(now)
        assert self._next_wakeup.tzinfo
        while not self._exited.is_set():
            self._sleep(dt.timedelta(seconds=5))

    def _sleep(self, max_sleep: dt.timedelta):
        now = dt.datetime.now(tz=dt.UTC)
        if self._next_wakeup <= now:
            self._callback()
            self._next_wakeup = self._get_next_wakeup_time(now)
        assert self._next_wakeup > now
        sleep_time = min(self._next_wakeup - now, max_sleep)
        time.sleep(sleep_time.total_seconds())

class TimerEvent:
    pass

class PeriodicWakeupController:
    def __init__(self, start_time: dt.datetime, period_time: dt.timedelta):
        assert start_time.tzinfo
        self.start_time = start_time
        self.period_time = period_time
        
    def next_wakeup(self, now: dt.datetime):
        delta_from_start = now - self.start_time
        seconds_left = self.period_time.total_seconds() - delta_from_start.total_seconds() % self.period_time.total_seconds()
        next_wakeup = now + dt.timedelta(seconds=seconds_left)
        return next_wakeup