"""
Utility functions for the Narrative Evolution Agent.
"""

import json
from typing import List, Dict, Any
from datetime import datetime, timedelta
import hashlib


def format_usd(amount: float) -> str:
    """Format USD amount with commas and decimals."""
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.2f}M"
    elif amount >= 1_000:
        return f"${amount / 1_000:.2f}K"
    else:
        return f"${amount:.2f}"


def get_momentum_emoji(trend: str) -> str:
    """Get emoji for narrative momentum trend."""
    emojis = {
        'strengthening': '📈',
        'weakening': '📉',
        'stable': '➡️',
        'emerging': '🌱',
        'new': '✨',
        'unknown': '❓'
    }
    return emojis.get(trend, '❓')


def get_strength_color(strength: str) -> str:
    """Get Streamlit color for narrative strength."""
    colors = {
        'High': '#2ecc71',
        'Medium': '#f39c12',
        'Low': '#e74c3c'
    }
    return colors.get(strength, '#95a5a6')


def calculate_time_ago(timestamp: str) -> str:
    """Convert ISO timestamp to human-readable 'time ago'."""
    if isinstance(timestamp, str):
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    else:
        dt = timestamp
    
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    diff = now - dt
    
    if diff.total_seconds() < 60:
        return "just now"
    elif diff.total_seconds() < 3600:
        minutes = int(diff.total_seconds() / 60)
        return f"{minutes}m ago"
    elif diff.total_seconds() < 86400:
        hours = int(diff.total_seconds() / 3600)
        return f"{hours}h ago"
    else:
        days = int(diff.total_seconds() / 86400)
        return f"{days}d ago"


def group_by_category(items: List[Dict[str, Any]], key: str) -> Dict[str, List]:
    """Group items by category."""
    grouped = {}
    for item in items:
        category = item.get(key, 'Unknown')
        if category not in grouped:
            grouped[category] = []
        grouped[category].append(item)
    return grouped


def sort_by_score(items: List[Dict[str, Any]], score_key: str = 'confidence_score', 
                 reverse: bool = True) -> List[Dict[str, Any]]:
    """Sort items by score."""
    return sorted(items, key=lambda x: x.get(score_key, 0), reverse=reverse)


def filter_by_confidence(items: List[Dict[str, Any]], 
                        min_confidence: float = 0.5) -> List[Dict[str, Any]]:
    """Filter items by minimum confidence score."""
    return [item for item in items if item.get('confidence_score', 0) >= min_confidence]


def calculate_volatility(history: List[Dict[str, Any]], 
                        value_key: str = 'confidence_score') -> float:
    """Calculate volatility (standard deviation) of values over time."""
    if len(history) < 2:
        return 0.0
    
    values = [h.get(value_key, 0) for h in history]
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return variance ** 0.5


def get_trend_direction(current: float, previous: float) -> str:
    """Determine trend direction."""
    if current > previous:
        return "📈 Up"
    elif current < previous:
        return "📉 Down"
    else:
        return "➡️ Stable"


def generate_narrative_id(name: str) -> str:
    """Generate a unique ID for a narrative."""
    return hashlib.md5(name.lower().encode()).hexdigest()[:12]


def parse_json_response(response_text: str) -> Dict[str, Any]:
    """Parse JSON response handling markdown code blocks."""
    text = response_text.strip()
    
    # Remove markdown code blocks if present
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
    
    return json.loads(text)


def format_narrative_card(narrative: Dict[str, Any]) -> str:
    """Format a narrative for display."""
    return f"""
**{narrative.get('name', 'Unknown')}**

Category: {narrative.get('category', 'N/A')} | Strength: {narrative.get('strength', 'N/A')}
Confidence: {narrative.get('confidence_score', 0):.1%} | Momentum: {narrative.get('momentum', {}).get('trend', 'unknown').title()}

*{narrative.get('implications', 'No implications available')}*
"""


def estimate_narrative_lifecycle(confidence_history: List[float]) -> str:
    """Estimate where a narrative is in its lifecycle."""
    if len(confidence_history) < 2:
        return "Emerging"
    
    recent = confidence_history[-3:]
    avg_recent = sum(recent) / len(recent)
    prev_avg = sum(confidence_history[:-3]) / max(len(confidence_history[:-3]), 1)
    
    if avg_recent > prev_avg * 1.2:
        return "Growth"
    elif avg_recent < prev_avg * 0.8:
        return "Decline"
    else:
        return "Mature"


def calculate_narrative_velocity(history: List[Dict[str, Any]]) -> float:
    """Calculate rate of change of confidence score."""
    if len(history) < 2:
        return 0.0
    
    scores = [h.get('confidence_score', 0) for h in sorted(history, key=lambda x: x.get('recorded_at', ''))]
    if len(scores) < 2:
        return 0.0
    
    return (scores[-1] - scores[0]) / len(scores)
