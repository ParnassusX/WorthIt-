import { useState } from 'react'
import './App.css'

function App() {
  const [imageUrl, setImageUrl] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState(null)

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

  return (
    <div className="app">
      <header className="app-header">
        <h1>WorthIt! Scanner</h1>
        <p>Scan products to analyze their value</p>
      </header>

      <main className="app-main">
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
      </main>
    </div>
  )
}

export default App