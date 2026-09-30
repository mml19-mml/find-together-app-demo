from dataclasses import dataclass, asdict
from datetime import datetime
from math import isfinite

@dataclass
class Monitor:
    """One subject, one active episode; distinct window endpoints count once."""
    last_timestamp: str = ''
    normal_count: int = 0
    had_alert: bool = False
    feedback_ready: bool = False
    status: str = 'monitoring'
    severity: str = 'normal'

    def observe(self, timestamp, loss, threshold, quality_ok=True):
        current = datetime.fromisoformat(timestamp)
        if current.tzinfo is None:
            raise ValueError('timestamp must include a timezone')
        if self.last_timestamp and current <= datetime.fromisoformat(self.last_timestamp):
            raise ValueError('duplicate or out-of-order timestamp')
        if not isfinite(loss) or not isfinite(threshold) or threshold <= 0 or loss < 0:
            raise ValueError('invalid score or threshold')
        if self.last_timestamp and (current - datetime.fromisoformat(self.last_timestamp)).total_seconds() != 60:
            self.normal_count = 0
            self.feedback_ready = False
        self.last_timestamp = timestamp
        if not quality_ok:
            self.normal_count = 0
            self.feedback_ready = False
            self.status = 'data_quality_issue'
            self.severity = 'unknown'
            return asdict(self)
        ratio = loss / threshold
        # Original prototype multipliers, not validated safety severity.
        self.severity = ('severe' if ratio >= 100 else 'medium' if ratio >= 50
                         else 'mild' if ratio >= 10 else 'deviation' if ratio > 1 else 'normal')
        if ratio > 1:
            self.had_alert = True
            self.normal_count = 0
            self.feedback_ready = False
            self.status = 'needs_review'
        elif self.had_alert:
            self.normal_count += 1
            self.feedback_ready = self.normal_count >= 31
            self.status = 'feedback_pending' if self.feedback_ready else 'recovering'
        else:
            self.status = 'monitoring'
        return asdict(self)

    def feedback(self, label):
        if not self.feedback_ready:
            raise ValueError('feedback requires more than 30 consecutive normal endpoints')
        if label not in ('confirmed_normal', 'confirmed_incident', 'uncertain'):
            raise ValueError('invalid feedback label')
        self.had_alert = False
        self.feedback_ready = False
        self.normal_count = 0
        self.status = 'monitoring'
        return {'label': label, 'eligible_for_reviewed_retraining': label == 'confirmed_normal'}

@dataclass
class SearchEvent:
    state: str = 'needs_review'
    search_level: int = 0

    def act(self, action):
        transitions = {
            ('needs_review', 'confirm_safe'): 'closed_false_alarm',
            ('needs_review', 'publish'): 'searching',
            ('searching', 'report_clue'): 'verifying',
            ('verifying', 'reject_clue'): 'searching',
            ('verifying', 'confirm_identity'): 'awaiting_pickup',
            ('awaiting_pickup', 'confirm_pickup'): 'closed_recovered',
        }
        key = (self.state, action)
        if action == 'escalate' and self.state == 'searching':
            self.search_level = min(4, self.search_level + 1)
        elif key in transitions:
            self.state = transitions[key]
            if action == 'publish': self.search_level = 1
        else:
            raise ValueError('action not valid for current state')
        return asdict(self)
