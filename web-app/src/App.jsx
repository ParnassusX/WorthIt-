import { useState, useEffect } from 'react'
import './App.css'
import Navigation from './components/Navigation'
import Profile from './components/Profile'
import SubscriptionStatus from './components/SubscriptionStatus'

function App() {
  const [currentPage, setCurrentPage] = useState('home')
  const [imageUrl, setImageUrl] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState(null)
  const [subscriptionStatus, setSubscriptionStatus] = useState(null)
  const [subscriptionTier, setSubscriptionTier] = useState(null)

  // Check for subscription status in URL params (for redirect from payment provider)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const status = params.get('subscription_status')
    const tier = params.get('tier')
    
    if (status) {
      setSubscriptionStatus(status)
      if (tier) setSubscriptionTier(tier)
      
      // Remove params from URL
      window.history.replaceState({}, document.title, window.location.pathname)
      
      // If returning from successful subscription, show profile page
      if (status === 'success') {
        setCurrentPage('profile')
      }
    }
  }, [])

  const handleNavigation = (page) => {
    setCurrentPage(page)
    // Reset scan state when navigating away from scan page
    if (page !== 'scan') {
      setImageUrl('')
      setResult(null)
    }
  }

  const handleCapture = async (e) => {
    try {
      setAnalyzing(true)
      const file = e.target.files[0]
      if (!file) return

      // Create a preview URL
      setImageUrl(URL.createObjectURL(file))

      // Prepare form data
      const formData = new FormData()
      formData.append('image', file)

      // Send to API
      const response = await fetch('/api/analyze-image', {
        method: 'POST',
        body: formData
      })

      const data = await response.json()
      setResult(data)
    } catch (error) {
      console.error('Error analyzing image:', error)
      setResult({ error: 'Failed to analyze image' })
    } finally {
      setAnalyzing(false)
    }
  }

  const renderContent = () => {
    switch (currentPage) {
      case 'profile':
        return <Profile />
      case 'scan':
        return (
          <div className="scan-container">
            {!imageUrl && (
              <div className="upload-area">
                <input
                  type="file"
                  accept="image/*"
                  capture="environment"
                  onChange={handleCapture}
                  className="file-input"
                  id="capture"
                />
                <label htmlFor="capture" className="capture-button">
                  📸 Scan Product
                </label>
              </div>
            )}

            {imageUrl && (
              <div className="preview-container">
                <img src={imageUrl} alt="Captured product" className="preview-image" />
                {analyzing && <div className="loading">Analyzing product... ⏳</div>}
              </div>
            )}

            {result && (
              <div className="result-container">
                <h2>{result.title || 'Analysis Results'}</h2>
                {result.error ? (
                  <div className="error">{result.error}</div>
                ) : (
                  <div className="analysis">
                    <div className="score">
                      Value Score: {result.valueScore}/10
                    </div>
                    <div className="price">
                      Estimated Price: {result.price}
                    </div>
                    <div className="recommendation">
                      {result.recommendation}
                    </div>
                  </div>
                )}
                <button
                  onClick={() => {
                    setImageUrl('')
                    setResult(null)
                  }}
                  className="scan-again-button"
                >
                  Scan Another Product
                </button>
              </div>
            )}
          </div>
        )
      case 'history':
        return <div className="history-container"><h2>Scan History</h2><p>Your scan history will appear here.</p></div>
      default: // home
        return (
          <div className="home-container">
            <h2>Welcome to WorthIt!</h2>
            <p>Use the navigation menu to scan products or view your profile.</p>
            <button onClick={() => handleNavigation('scan')} className="start-scan-button">
              Start Scanning
            </button>
          </div>
        )
    }
  }

  return (
    <div className="app">
      <Navigation onNavigate={handleNavigation} />
      
      <SubscriptionStatus status={subscriptionStatus} tier={subscriptionTier} />
      
      <main className="app-main">
        {renderContent()}
      </main>

      <footer className="app-footer">
        <p>© 2023 WorthIt! - All rights reserved</p>
      </footer>
    </div>
  )
}

export default App