import { useState, useEffect } from 'react';
import './SubscriptionStatus.css';

function SubscriptionStatus({ status, tier }) {
  const [visible, setVisible] = useState(true);
  
  useEffect(() => {
    // Show notification for 5 seconds then fade out
    if (status) {
      setVisible(true);
      const timer = setTimeout(() => {
        setVisible(false);
      }, 5000);
      
      return () => clearTimeout(timer);
    }
  }, [status]);
  
  if (!status) return null;
  
  const getStatusMessage = () => {
    switch (status) {
      case 'success':
        return `Successfully subscribed to ${tier} plan!`;
      case 'pending':
        return 'Processing your subscription...';
      case 'failed':
        return 'Subscription payment failed. Please try again.';
      case 'cancelled':
        return 'Subscription cancelled.';
      default:
        return 'Subscription status updated.';
    }
  };
  
  const getStatusClass = () => {
    switch (status) {
      case 'success':
        return 'success';
      case 'pending':
        return 'pending';
      case 'failed':
        return 'error';
      case 'cancelled':
        return 'warning';
      default:
        return 'info';
    }
  };
  
  return (
    <div className={`subscription-status ${getStatusClass()} ${visible ? 'visible' : 'hidden'}`}>
      <div className="status-icon">
        {status === 'success' && '✓'}
        {status === 'pending' && '⏳'}
        {status === 'failed' && '✗'}
        {status === 'cancelled' && '!'}
        {!['success', 'pending', 'failed', 'cancelled'].includes(status) && 'ℹ'}
      </div>
      <div className="status-message">
        {getStatusMessage()}
      </div>
      <button className="close-button" onClick={() => setVisible(false)}>×</button>
    </div>
  );
}

export default SubscriptionStatus;