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

// API endpoint - updated to use deployed API endpoint
const API_URL = '/api/analyze';

// Event listeners
analyzeBtn.addEventListener('click', analyzeProduct);

// Camera functionality
const cameraBtn = document.getElementById('camera-btn');
const cameraInput = document.getElementById('camera-input');

cameraBtn.addEventListener('click', () => {
    cameraInput.click();
});

cameraInput.addEventListener('change', async (event) => {
    if (event.target.files && event.target.files[0]) {
        const file = event.target.files[0];
        
        // Show loading state
        resultEl.style.display = 'none';
        loadingDiv.style.display = 'block';
        
        try {
            // Create FormData to send the image
            const formData = new FormData();
            formData.append('image', file);
            
            // Call the API endpoint for image processing
            const response = await fetch('/api/analyze-image', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }
            
            const data = await response.json();
            displayResults(data);
        } catch (error) {
            console.error('Error processing image:', error);
            alert('Si è verificato un errore durante l\'elaborazione dell\'immagine. Riprova più tardi.');
        } finally {
            loadingDiv.style.display = 'none';
        }
    }
});

// Main function to analyze product
async function analyzeProduct() {
    const productUrl = productUrlInput.value.trim();
    
    if (!productUrl) {
        alert('Per favore, inserisci un URL valido');
        return;
    }
    
    // Show loading state
    resultEl.style.display = 'none';
    loadingDiv.style.display = 'block';
    
    try {
        // Call the API
        const response = await fetch(`${API_URL}?url=${encodeURIComponent(productUrl)}`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Display results
        displayResults(data);
    } catch (error) {
        console.error('Error analyzing product:', error);
        alert('Si è verificato un errore durante l\'analisi del prodotto. Riprova più tardi.');
    } finally {
        loadingDiv.style.display = 'none';
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