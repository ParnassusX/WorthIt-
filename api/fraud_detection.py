"""Fraud detection module for payment transactions."""

import logging
import time
from typing import Dict, Any, List, Tuple, Optional
import ipaddress
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory storage for demonstration
# In production, this should be stored in a database
SUSPICIOUS_ACTIVITIES = []
BLOCKED_IPS = set()
USER_PAYMENT_HISTORY = {}
FRAUD_PATTERNS = [
    {"name": "multiple_cards", "threshold": 3, "timeframe": 3600},  # 3 different cards in 1 hour
    {"name": "rapid_transactions", "threshold": 5, "timeframe": 300},  # 5 transactions in 5 minutes
    {"name": "amount_velocity", "threshold": 1000, "timeframe": 86400},  # $1000 in 24 hours
    {"name": "location_change", "threshold": 2, "timeframe": 3600},  # Location change in 1 hour
]


class FraudDetector:
    """Fraud detection system for payment transactions."""
    
    def __init__(self):
        self.risk_threshold = 0.7  # Risk score threshold for flagging transactions
        self.high_risk_countries = ["XX", "YY", "ZZ"]  # Example high-risk country codes
        self.suspicious_ip_ranges = [
            "192.168.0.0/16",  # Example ranges, should be replaced with actual suspicious ranges
            "10.0.0.0/8"
        ]
        self.suspicious_ip_networks = [
            ipaddress.ip_network(cidr) for cidr in self.suspicious_ip_ranges
        ]
        
        # Enhanced fraud detection settings
        self.ml_model_enabled = False  # Set to True when ML model is available
        self.behavioral_analysis_enabled = True
        self.real_time_scoring_enabled = True
        self.max_daily_transaction_amount = 5000  # Maximum amount per day per user
    
    def analyze_transaction(self, transaction: Dict[str, Any], user_id: str, 
                           ip_address: str) -> Tuple[bool, float, Optional[str]]:
        """Analyze a transaction for potential fraud.
        
        Args:
            transaction: Transaction details including amount, card info, etc.
            user_id: ID of the user making the transaction
            ip_address: IP address of the user
            
        Returns:
            Tuple of (is_fraudulent, risk_score, reason)
        """
        risk_score = 0.0
        risk_factors = []
        
        # Check if IP is in blocked list
        if ip_address in BLOCKED_IPS:
            return True, 1.0, "IP address is blocked due to previous fraudulent activity"
        
        # Check if IP is in suspicious range
        try:
            ip = ipaddress.ip_address(ip_address)
            for network in self.suspicious_ip_networks:
                if ip in network:
                    risk_score += 0.3
                    risk_factors.append("IP in suspicious range")
                    break
        except ValueError:
            # Invalid IP format
            risk_score += 0.1
            risk_factors.append("Invalid IP format")
        
        # Check transaction amount
        amount = transaction.get("amount", 0)
        if amount > 1000:
            risk_score += 0.2
            risk_factors.append("High transaction amount")
        
        # Check for velocity (multiple transactions in short time)
        if self._check_transaction_velocity(user_id):
            risk_score += 0.3
            risk_factors.append("Multiple transactions in short time")
        
        # Check for multiple payment methods
        if self._check_multiple_payment_methods(user_id, transaction):
            risk_score += 0.3
            risk_factors.append("Multiple payment methods used recently")
        
        # Check for unusual location
        if self._check_unusual_location(user_id, transaction):
            risk_score += 0.2
            risk_factors.append("Unusual location for user")
        
        # Record this transaction for future checks
        self._record_transaction(user_id, transaction, ip_address)
        
        # Determine if fraudulent based on risk score
        is_fraudulent = risk_score >= self.risk_threshold
        reason = ", ".join(risk_factors) if risk_factors else None
        
        if is_fraudulent:
            self._record_suspicious_activity(user_id, transaction, ip_address, risk_score, reason)
        
        return is_fraudulent, risk_score, reason
    
    def _check_transaction_velocity(self, user_id: str) -> bool:
        """Check if user has made too many transactions in a short time."""
        if user_id not in USER_PAYMENT_HISTORY:
            return False
        
        recent_transactions = []
        current_time = time.time()
        
        for tx in USER_PAYMENT_HISTORY[user_id]:
            if current_time - tx["timestamp"] < 300:  # 5 minutes
                recent_transactions.append(tx)
        
        return len(recent_transactions) >= 5  # 5 or more transactions in 5 minutes
    
    def _check_multiple_payment_methods(self, user_id: str, transaction: Dict[str, Any]) -> bool:
        """Check if user has used multiple payment methods recently."""
        if user_id not in USER_PAYMENT_HISTORY:
            return False
        
        current_time = time.time()
        recent_cards = set()
        
        # Get current card identifier (last 4 digits)
        current_card = transaction.get("card_last4", "")
        if not current_card:
            return False
        
        # Check recent transactions
        for tx in USER_PAYMENT_HISTORY[user_id]:
            if current_time - tx["timestamp"] < 3600:  # 1 hour
                if "card_last4" in tx:
                    recent_cards.add(tx["card_last4"])
        
        # Add current card
        recent_cards.add(current_card)
        
        return len(recent_cards) >= 3  # 3 or more cards in 1 hour
    
    def _check_unusual_location(self, user_id: str, transaction: Dict[str, Any]) -> bool:
        """Check if transaction location is unusual for this user."""
        if user_id not in USER_PAYMENT_HISTORY or not USER_PAYMENT_HISTORY[user_id]:
            return False
        
        # Get current country code
        current_country = transaction.get("country_code", "")
        if not current_country:
            return False
        
        # Check if country is in high-risk list
        if current_country in self.high_risk_countries:
            return True
        
        # Get most recent transaction country
        most_recent = max(USER_PAYMENT_HISTORY[user_id], key=lambda x: x["timestamp"])
        previous_country = most_recent.get("country_code", "")
        
        # If countries don't match and transaction is within 1 hour, flag as unusual
        if (previous_country and 
            previous_country != current_country and 
            time.time() - most_recent["timestamp"] < 3600):
            return True
        
        return False
    
    def _record_transaction(self, user_id: str, transaction: Dict[str, Any], ip_address: str):
        """Record transaction for future fraud checks."""
        if user_id not in USER_PAYMENT_HISTORY:
            USER_PAYMENT_HISTORY[user_id] = []
        
        # Create a record with timestamp
        record = transaction.copy()
        record["timestamp"] = time.time()
        record["ip_address"] = ip_address
        
        USER_PAYMENT_HISTORY[user_id].append(record)
        
        # Limit history size
        if len(USER_PAYMENT_HISTORY[user_id]) > 100:
            USER_PAYMENT_HISTORY[user_id] = USER_PAYMENT_HISTORY[user_id][-100:]
    
    def _record_suspicious_activity(self, user_id: str, transaction: Dict[str, Any], 
                                   ip_address: str, risk_score: float, reason: str):
        """Record suspicious activity for review."""
        SUSPICIOUS_ACTIVITIES.append({
            "user_id": user_id,
            "transaction_id": transaction.get("id", "unknown"),
            "amount": transaction.get("amount", 0),
            "ip_address": ip_address,
            "timestamp": time.time(),
            "risk_score": risk_score,
            "reason": reason
        })
        
        # If very high risk, block the IP
        if risk_score > 0.9:
            BLOCKED_IPS.add(ip_address)
            logger.warning(f"Blocked IP {ip_address} due to high-risk transaction")


# Singleton instance
fraud_detector = FraudDetector()


def check_transaction(transaction: Dict[str, Any], user_id: str, 
                     ip_address: str) -> Tuple[bool, float, Optional[str]]:
    """Check if a transaction is potentially fraudulent.
    
    Args:
        transaction: Transaction details
        user_id: User ID
        ip_address: IP address of the user
        
    Returns:
        Tuple of (is_fraudulent, risk_score, reason)
    """
    return fraud_detector.analyze_transaction(transaction, user_id, ip_address)


def get_suspicious_activities(hours: int = 24) -> List[Dict[str, Any]]:
    """Get list of suspicious activities within the specified time window.
    
    Args:
        hours: Number of hours to look back
        
    Returns:
        List of suspicious activities
    """
    cutoff_time = time.time() - (hours * 3600)
    return [activity for activity in SUSPICIOUS_ACTIVITIES if activity["timestamp"] > cutoff_time]


def clear_user_history(user_id: str) -> bool:
    """Clear transaction history for a user.
    
    Args:
        user_id: User ID to clear history for
        
    Returns:
        True if successful, False otherwise
    """
    if user_id in USER_PAYMENT_HISTORY:
        del USER_PAYMENT_HISTORY[user_id]
        return True
    return False