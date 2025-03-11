import { useState, useEffect } from 'react';
import './Profile.css';

function Profile() {
  const [userProfile, setUserProfile] = useState(null);
  const [subscription, setSubscription] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchUserProfile();
  }, []);

  const fetchUserProfile = async () => {
    try {
      // TODO: Replace with actual API endpoint
      const response = await fetch('/api/user/profile');
      const data = await response.json();
      setUserProfile(data);
      setSubscription(data.subscription);
    } catch (error) {
      console.error('Error fetching profile:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubscribe = async (tier) => {
    try {
      const response = await fetch('/api/payment/subscription/create', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ tier }),
      });
      const data = await response.json();
      
      // Redirect to payment page
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch (error) {
      console.error('Error creating subscription:', error);
    }
  };

  if (loading) {
    return <div className="profile-loading">Loading profile...</div>;
  }

  return (
    <div className="profile-container">
      <div className="profile-header">
        <h2>My Profile</h2>
      </div>

      <div className="profile-info">
        {userProfile && (
          <>
            <div className="user-details">
              <h3>{userProfile.name}</h3>
              <p>{userProfile.email}</p>
            </div>

            <div className="subscription-details">
              <h3>Subscription Status</h3>
              {subscription ? (
                <div className="current-plan">
                  <p>Current Plan: {subscription.tier}</p>
                  <p>Status: {subscription.status}</p>
                  <p>Next billing date: {subscription.nextBillingDate}</p>
                </div>
              ) : (
                <div className="no-subscription">
                  <p>No active subscription</p>
                  <div className="subscription-options">
                    <button onClick={() => handleSubscribe('basic')}>Subscribe to Basic</button>
                    <button onClick={() => handleSubscribe('premium')}>Subscribe to Premium</button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default Profile;