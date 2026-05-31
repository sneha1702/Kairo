"""
Example usage and testing script for the Narrative Evolution Agent.
Run this to test the system without the Streamlit UI.
"""

import json
import os
from datetime import datetime, timedelta
from app.brain.elasticsearch_manager import ElasticsearchManager
from app.synthesize.narrative_engine import NarrativeEngine
from app.synthesize.narrative_tracker import NarrativeTracker
from app.brain.config import Config, NarrativeConfig
from utils.utils import format_usd, get_momentum_emoji


def print_section(title: str):
    """Print formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def example_1_load_data():
    """Example 1: Load and explore whale data."""
    print_section("Example 1: Load and Explore Whale Data")
    
    try:
        es = ElasticsearchManager(
            Config.ES_URL,
            Config.ES_USERNAME,
            Config.ES_PASSWORD,
            Config.ES_API_KEY_ID,
        )
        
        print("📊 Fetching recent whale transactions...")
        transactions = es.get_recent_transactions(hours=24, min_usd=10000)
        
        print(f"✅ Found {len(transactions)} significant transactions\n")
        
        print("Recent transactions:")
        for tx in transactions[:3]:
            amount_usd = tx.get('amount_usd')
            amount_usd = float(amount_usd) if amount_usd is not None else 0.0
            print(f"  • {tx.get('wallet', 'Unknown')[:10]}... bought {tx.get('token')} for {format_usd(amount_usd)}")
        
        # Category breakdown
        print("\n📈 Activity by Category:")
        category_activity = es.get_category_activity(hours=24)
        for category, data in category_activity.items():
            print(f"  {category}: {format_usd(data['volume'])} ({data['tx_count']} txs)")
        
        # Top whales
        print("\n🐋 Top Active Whales:")
        whales = es.get_top_active_whales(hours=24, limit=5)
        for i, whale in enumerate(whales, 1):
            print(f"  {i}. {whale['wallet'][:10]}... - {format_usd(whale['volume'])} traded")
        
        # Emerging tokens
        print("\n🚀 Emerging Tokens (24h):")
        emerging = es.get_emerging_tokens(hours=24, min_transactions=3)
        for token in emerging[:5]:
            print(f"  • {token['token']}: {token['whale_count']} whales, {format_usd(token['volume'])} volume")
        
        return transactions
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return []


def example_2_detect_narratives(transactions):
    """Example 2: Detect narratives using Gemini."""
    print_section("Example 2: Detect Narratives from Whale Activity")
    
    try:
        engine = NarrativeEngine(Config.GEMINI_KEY)
        
        print("📊 Grouping whale activity...")
        whale_activity = engine.group_whale_activity(transactions)
        
        print(f"✅ Grouped into {len(whale_activity)} categories\n")
        
        print("🔍 Detecting narratives with Gemini...")
        narratives = engine.detect_narratives(whale_activity)
        
        print(f"✅ Detected {len(narratives)} narratives\n")
        
        for i, narrative in enumerate(narratives, 1):
            print(f"📌 Narrative #{i}: {narrative.get('name')}")
            print(f"   Category: {narrative.get('category')}")
            print(f"   Strength: {narrative.get('strength')}")
            print(f"   Confidence: {narrative.get('confidence_score', 0):.1%}")
            print(f"   Top Tokens: {', '.join(narrative.get('top_tokens', [])[:3])}")
            print(f"   Implications: {narrative.get('implications', 'N/A')[:100]}...")
            print()
        
        return narratives
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return []


def example_3_track_narratives(narratives, transactions):
    """Example 3: Track narratives over time."""
    print_section("Example 3: Track Narratives Over Time")
    
    try:
        es = ElasticsearchManager(
            Config.ES_URL,
            Config.ES_USERNAME,
            Config.ES_PASSWORD,
            Config.ES_API_KEY_ID,
        )
        tracker = NarrativeTracker(Config.MONGO_URI, Config.MONGO_DB)
        engine = NarrativeEngine(Config.GEMINI_KEY)
        
        # Enrich narratives with momentum
        print("📈 Enriching narratives with momentum analysis...")
        enriched = []
        for narrative in narratives:
            enriched_narrative = engine.enrich_narrative(narrative)
            enriched.append(enriched_narrative)
        
        # Save to tracker
        print("💾 Saving narratives to Elasticsearch...")
        tracker.save_narratives(enriched, user_id="example")
        
        # Track some narratives
        print("\n⭐ Tracking first narrative...")
        if enriched:
            tracker.track_narrative(enriched[0].get('name'), user_id="example")
        
        # Get tracked narratives
        print("\n📋 Your tracked narratives:")
        tracked = tracker.get_tracked_narratives(user_id="example")
        for narrative in tracked:
            momentum = narrative.get('momentum', {})
            emoji = get_momentum_emoji(momentum.get('trend', 'unknown'))
            print(f"  {emoji} {narrative.get('name')} ({narrative.get('category')})")
            print(f"     Confidence: {narrative.get('confidence_score', 0):.1%}")
            print(f"     Momentum: {momentum.get('trend', 'unknown')}")
        
        # Get stats
        print("\n📊 Narrative Statistics:")
        stats = tracker.get_narrative_stats(user_id="example")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        return tracker
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def example_4_analyze_history():
    """Example 4: Analyze narrative history."""
    print_section("Example 4: Analyze Narrative History")
    
    try:
        es = ElasticsearchManager(
            Config.ES_URL,
            Config.ES_USERNAME,
            Config.ES_PASSWORD,
            Config.ES_API_KEY_ID
        )
        tracker = NarrativeTracker(Config.MONGO_URI, Config.MONGO_DB)
        
        # Get all narratives
        all_narratives = tracker.get_current_narratives(user_id="example", min_confidence=0.0)
        
        if not all_narratives:
            print("No narratives found. Run examples 1-3 first.")
            return
        
        # Analyze first narrative
        narrative = all_narratives[0]
        narrative_name = narrative.get('name')
        if not isinstance(narrative_name, str):
            print("No narrative name available. Cannot fetch history.")
            return
        print(f"📊 Analyzing narrative: {narrative_name}\n")
        
        # Get history
        history = tracker.get_narrative_history(
            narrative_name,
            days=7,
            user_id="example"
        )
        
        if history:
            print(f"✅ Found {len(history)} historical records\n")
            
            # Calculate stats
            confidence_scores = [h.get('confidence_score', 0) for h in history]
            momentum_scores = [h.get('momentum_score', 0) for h in history]
            
            print("📈 Historical Statistics:")
            print(f"  Average Confidence: {sum(confidence_scores)/len(confidence_scores):.1%}")
            print(f"  Max Confidence: {max(confidence_scores):.1%}")
            print(f"  Min Confidence: {min(confidence_scores):.1%}")
            print(f"  Average Momentum: {sum(momentum_scores)/len(momentum_scores):.1%}")
            
            # Trend
            if len(confidence_scores) > 1:
                change = confidence_scores[-1] - confidence_scores[0]
                direction = "📈 UP" if change > 0 else "📉 DOWN" if change < 0 else "➡️ STABLE"
                print(f"  7-Day Trend: {direction} ({change:+.1%})")
        else:
            print("No historical data available yet.")
    
    except Exception as e:
        print(f"❌ Error: {e}")


def example_5_get_strengthening_narratives():
    """Example 5: Get currently strengthening narratives."""
    print_section("Example 5: Get Strengthening Narratives")
    
    try:
        es = ElasticsearchManager(
            Config.ES_URL,
            Config.ES_USERNAME,
            Config.ES_PASSWORD,
            Config.ES_API_KEY_ID
        )
        tracker = NarrativeTracker(Config.MONGO_URI, Config.MONGO_DB)
        
        print("📈 Fetching strengthening narratives...\n")
        strengthening = tracker.get_strengthening_narratives(user_id="example")
        
        if strengthening:
            print(f"✅ Found {len(strengthening)} strengthening narratives\n")
            
            for i, narrative in enumerate(strengthening[:5], 1):
                momentum = narrative.get('momentum', {})
                print(f"{i}. {narrative.get('name')}")
                print(f"   Momentum Score: {momentum.get('momentum_score', 0):.1%}")
                print(f"   Confidence Change: {momentum.get('confidence_change', 0):+.1%}")
                print(f"   Strength Change: {momentum.get('strength_change', 0):+.0f}")
                print()
        else:
            print("No strengthening narratives found.")
    
    except Exception as e:
        print(f"❌ Error: {e}")


def main():
    """Run all examples."""
    print("\n" + "="*60)
    print("  🔮 Narrative Evolution Agent - Example Usage")
    print("="*60)
    
    # Check configuration
    print("\n✓ Configuration loaded:")
    print(f"  ES URL: {Config.ES_URL[:50]}...")
    print(f"  Gemini Model: {Config.GEMINI_MODEL}")
    
    # Run examples
    try:
        # Example 1: Load data
        print("\n[1/5] Loading whale data...")
        transactions = example_1_load_data()
        
        if not transactions:
            print("\n⚠️  No transactions found. Make sure to run:")
            print("   python ingest.py")
            return
        
        # Example 2: Detect narratives
        print("\n[2/5] Detecting narratives...")
        narratives = example_2_detect_narratives(transactions)
        
        if not narratives:
            print("\n⚠️  No narratives detected.")
            return
        
        # Example 3: Track narratives
        print("\n[3/5] Tracking narratives...")
        tracker = example_3_track_narratives(narratives, transactions)
        
        # Example 4: Analyze history
        print("\n[4/5] Analyzing narrative history...")
        example_4_analyze_history()
        
        # Example 5: Get strengthening narratives
        print("\n[5/5] Getting strengthening narratives...")
        example_5_get_strengthening_narratives()
        
        print_section("✅ All Examples Completed")
        print("Now run: streamlit run app.py")
    
    except KeyboardInterrupt:
        print("\n\n🛑 Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
