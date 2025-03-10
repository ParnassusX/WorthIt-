// Initialize Telegram WebApp
const tg = window.Telegram.WebApp;
tg.expand();

// DOM elements
const productUrlInput = document.getElementById('product-url');
const analyzeBtn = document.getElementById('analyze-btn');
const resultEl = document.getElementById('result');
const loadingDiv = document.getElementById('loading');
const productTitle = document.getElementById('product-title');
const valueScoreEl = document.getElementById('value-score');
const recommendationEl = document.getElementById('recommendation');
const prosList = document.getElementById('pros');
const consList = document.getElementById('cons');

// API endpoint - updated to use Netlify Functions endpoint with absolute path
const API_URL = window.location.origin + '/.netlify/functions/analyze';
console.log('Using API URL:', API_URL);

// Event listeners
analyzeBtn.addEventListener('click', analyzeProduct);

// Camera functionality
const cameraBtn = document.getElementById('camera-btn');
const cameraInput = document.getElementById('camera-input');

cameraBtn.addEventListener('click', () => {
    cameraInput.click();
});

// Utility function for retry logic with circuit breaker
const retryFetch = async (url, options, maxRetries = 3, backoffMs = 1000) => {
    let lastError;
    const circuitBreaker = {
        failures: 0,
        lastFailure: null,
        threshold: 5,
        resetTimeout: 30000
    };
    
    // Check circuit breaker
    if (circuitBreaker.failures >= circuitBreaker.threshold) {
        if (Date.now() - circuitBreaker.lastFailure < circuitBreaker.resetTimeout) {
            throw new Error('Circuit breaker is open');
        }
        // Reset circuit breaker
        circuitBreaker.failures = 0;
    }
    
    for (let attempt = 0; attempt < maxRetries; attempt++) {
        try {
            const response = await fetch(url, options);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            // Reset circuit breaker on success
            circuitBreaker.failures = 0;
            return response;
        } catch (error) {
            lastError = error;
            circuitBreaker.failures++;
            circuitBreaker.lastFailure = Date.now();
            errorTracker.track(error, { url, attempt });
            
            if (attempt < maxRetries - 1) {
                const backoff = backoffMs * Math.pow(2, attempt);
                await new Promise(resolve => setTimeout(resolve, backoff));
            }
        }
    }
    throw lastError;
};

// Error tracking utility
const errorTracker = {
    errors: [],
    maxErrors: 50,
    track(error, context = {}) {
        const errorInfo = {
            timestamp: new Date().toISOString(),
            error: error.message,
            stack: error.stack,
            context
        };
        this.errors.push(errorInfo);
        if (this.errors.length > this.maxErrors) {
            this.errors.shift();
        }
        // Send error to monitoring service
        this.reportError(errorInfo);
    },
    async reportError(errorInfo) {
        try {
            await fetch('/.netlify/functions/log-error', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(errorInfo)
            });
        } catch (e) {
            console.error('Failed to report error:', e);
        }
    }
};

// Enhanced error handling
const handleError = (error) => {
    errorTracker.track(error);
    let userMessage = 'Si è verificato un errore. Riprova più tardi.';
    
    if (error.message.includes('Circuit breaker is open')) {
        userMessage = 'Il servizio è temporaneamente non disponibile. Riprova tra qualche minuto.';
    } else if (error.message.includes('NetworkError') || error.message.includes('Failed to fetch')) {
        userMessage = 'Errore di connessione. Verifica la tua connessione internet e riprova.';
    } else if (error.message.includes('HTTP error! status: 429')) {
        userMessage = 'Troppe richieste. Attendi qualche minuto e riprova.';
    } else if (error.message.includes('HTTP error! status: 4')) {
        userMessage = 'Errore nella richiesta. Verifica l\'URL del prodotto e riprova.';
    } else if (error.message.includes('HTTP error! status: 5')) {
        userMessage = 'Il servizio non è al momento disponibile. Riprova più tardi.';
    }
    
    // Show error in UI
    const errorEl = document.getElementById('error-message');
    if (errorEl) {
        errorEl.textContent = userMessage;
        errorEl.style.display = 'block';
        setTimeout(() => {
            errorEl.style.display = 'none';
        }, 5000);
    } else {
        alert(userMessage);
    }
};

// Update loading state management
const setLoadingState = (isLoading) => {
    if (isLoading) {
        resultEl.style.display = 'none';
        loadingDiv.style.display = 'block';
        analyzeBtn.disabled = true;
        productUrlInput.disabled = true;
    } else {
        loadingDiv.style.display = 'none';
        analyzeBtn.disabled = false;
        productUrlInput.disabled = false;
    }
};

// Update camera input handler
cameraInput.addEventListener('change', async (event) => {
    if (event.target.files && event.target.files[0]) {
        const file = event.target.files[0];
        setLoadingState(true);
        
        try {
            const formData = new FormData();
            formData.append('image', file);
            
            const response = await retryFetch('/.netlify/functions/analyze-image', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            displayResults(data);
        } catch (error) {
            handleError(error);
        } finally {
            setLoadingState(false);
        }
    }
});

// Update main analyze function
async function analyzeProduct() {
    const productUrl = productUrlInput.value.trim();
    
    if (!productUrl) {
        alert('Per favore, inserisci un URL valido');
        return;
    }
    
    setLoadingState(true);
    
    try {
        const response = await retryFetch(`${API_URL}?url=${encodeURIComponent(productUrl)}`, {
            method: 'POST'
        });
        
        const data = await response.json();
        displayResults(data);
    } catch (error) {
        handleError(error);
    } finally {
        setLoadingState(false);
    }
}

// Display results in the UI
function displayResults(data) {
    // Set product info
    productTitle.textContent = data.title;
    
    // Set value score with emoji indicator
    const valueScore = data.value_score;
    let valueEmoji = '🔴'; // Default red
    
    if (valueScore >= 7) {
        valueEmoji = '🟢'; // Green for good value
    } else if (valueScore >= 5) {
        valueEmoji = '🟡'; // Yellow for medium value
    }
    
    valueScoreEl.textContent = `Valore: ${valueEmoji} ${valueScore.toFixed(1)}/10`;
    
    // Set recommendation
    recommendationEl.textContent = data.recommendation;
    
    // Clear previous lists
    prosList.innerHTML = '';
    consList.innerHTML = '';
    
    // Extract pros and cons from analysis text or use provided pros/cons
    let pros = [];
    let cons = [];
    
    // Check if the API directly provided pros and cons arrays
    if (data.pros && Array.isArray(data.pros)) {
        pros = data.pros;
    } else if (data.analysis) {
        // Simple parsing of pros/cons from the generated text
        const lines = data.analysis.split('\n');
        let currentSection = null;
        
        for (const line of lines) {
        const trimmedLine = line.trim();
        if (trimmedLine.toLowerCase().includes('pros:') || 
            trimmedLine.toLowerCase().includes('advantages:') || 
            trimmedLine.toLowerCase().includes('strengths:')) {
            currentSection = 'pros';
            continue;
        } else if (trimmedLine.toLowerCase().includes('cons:') || 
                 trimmedLine.toLowerCase().includes('disadvantages:') || 
                 trimmedLine.toLowerCase().includes('weaknesses:')) {
            currentSection = 'cons';
            continue;
        }
        
        if (currentSection === 'pros' && trimmedLine && !trimmedLine.toLowerCase().startsWith('cons')) {
            if (trimmedLine.startsWith('-') || trimmedLine.startsWith('*')) {
                pros.push(trimmedLine.replace(/^[-*]\s*/, '').charAt(0).toUpperCase() + trimmedLine.replace(/^[-*]\s*/, '').slice(1));
            } else if (pros.length < 3 && trimmedLine) { // Backup if no bullet points
                pros.push(trimmedLine.charAt(0).toUpperCase() + trimmedLine.slice(1));
            }
        }
        
        if (currentSection === 'cons' && trimmedLine) {
            if (trimmedLine.startsWith('-') || trimmedLine.startsWith('*')) {
                cons.push(trimmedLine.replace(/^[-*]\s*/, '').charAt(0).toUpperCase() + trimmedLine.replace(/^[-*]\s*/, '').slice(1));
            } else if (cons.length < 3 && trimmedLine) { // Backup if no bullet points
                cons.push(trimmedLine.charAt(0).toUpperCase() + trimmedLine.slice(1));
            }
        }
    }
    }
    
    // Ensure we have at least some pros and cons
    if (pros.length === 0) {
        pros.push('Informazioni insufficienti');
    }
    if (cons.length === 0) {
        cons.push('Informazioni insufficienti');
    }
    
    // Add pros
    pros.slice(0, 3).forEach(pro => {
        const li = document.createElement('li');
        li.textContent = pro;
        prosList.appendChild(li);
    });
    
    // Add cons
    cons.slice(0, 3).forEach(con => {
        const li = document.createElement('li');
        li.textContent = con;
        consList.appendChild(li);
    });
    
    // Show results
    resultEl.style.display = 'block';
    
    // Send data back to Telegram if in Telegram WebApp
    if (tg.initDataUnsafe?.query_id) {
        tg.sendData(JSON.stringify({
            url: productUrlInput.value,
            title: data.title,
            value_score: valueScore,
            recommendation: data.recommendation
        }));
    }
}



// Mock data for demo purposes
async function getMockData(url) {
    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 1500));
    
    return {
        title: 'iPhone 11 Ricondizionato',
        price: 219.00,
        value_score: 3.8,
        pros: [
            '92% recensioni positive',
            'Batteria sostituita in 80% casi',
            'Garanzia di 12 mesi inclusa'
        ],
        cons: [
            '12% segnala difetti estetici',
            'Accessori non originali in alcuni casi',
            'Variabilità nella qualità tra venditori'
        ],
        alternatives: [
            {
                title: 'Samsung S20 FE',
                price: 249.00,
                value_score: 4.1
            }
        ]
    };
}