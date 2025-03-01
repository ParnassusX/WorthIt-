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

// API endpoint - updated to use local FastAPI server
const API_URL = 'http://localhost:8000/analyze';

// Event listeners
analyzeBtn.addEventListener('click', analyzeProduct);

// Main function to analyze product
async function analyzeProduct() {
    const productUrl = productUrlInput.value.trim();
    
    if (!productUrl) {
        alert('Per favore, inserisci un URL o codice prodotto valido');
        return;
    }
    
    // Show loading state
    resultEl.style.display = 'none';
    loadingDiv.style.display = 'block';
    
    try {
        // Call the local API
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: productUrl })
        });
        
        // If API call fails, use mock data for demo purposes
        let data;
        if (!response.ok) {
            console.warn('API call failed, using mock data instead');
            data = await getMockData(productUrl);
        } else {
            data = await response.json();
        }
        
        // Display results
        displayResults(data);
    } catch (error) {
        console.error('Error analyzing product:', error);
        alert('Si è verificato un errore durante l\'analisi del prodotto. Riprova più tardi.');
        
        // For demo purposes, still show mock data even if there's an error
        const mockData = await getMockData(productUrl);
        displayResults(mockData);
    } finally {
        loadingDiv.style.display = 'none';
    }
}

// Display results in the UI
function displayResults(data) {
    // Set product info
    productTitle.textContent = data.title;
    
    // Set value score
    valueScoreEl.textContent = `Valore: ${data.value_score.toFixed(1)}/5.0`;
    
    // Set recommendation
    if (data.value_score >= 4) {
        recommendationEl.textContent = 'Vale il prezzo? SÌ!';
    } else if (data.value_score >= 3) {
        recommendationEl.textContent = 'Vale il prezzo? FORSE';
    } else {
        recommendationEl.textContent = 'Vale il prezzo? NO';
    }
    
    // Clear previous lists
    prosList.innerHTML = '';
    consList.innerHTML = '';
    
    // Add pros
    data.pros.forEach(pro => {
        const li = document.createElement('li');
        li.textContent = pro;
        prosList.appendChild(li);
    });
    
    // Add cons
    data.cons.forEach(con => {
        const li = document.createElement('li');
        li.textContent = con;
        consList.appendChild(li);
    });
    
    // Show results
    resultEl.style.display = 'block';
    
    // Notify Telegram app that we're done
    tg.MainButton.setText('Condividi Risultato');
    tg.MainButton.show();
    tg.MainButton.onClick(() => {
        tg.sendData(JSON.stringify({
            product_url: productUrlInput.value,
            analysis: data
        }));
    });
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