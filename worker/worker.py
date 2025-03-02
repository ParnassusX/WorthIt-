import asyncio
import os
import logging
from telegram import Bot
from dotenv import load_dotenv
from typing import Dict, Any

# Import the queue interface
from worker.queue import get_task_queue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

async def process_task(task: Dict[str, Any], bot: Bot) -> None:
    """Process a single task from the queue"""
    try:
        logger.info(f"Processing task: {task['task_type']}")
        
        if task['task_type'] == 'product_analysis':
            # Import here to avoid circular imports
            from api.main import analyze_product
            from api.scraper import ProductScraper
            from api.ml_processor import MLProcessor
            
            # Send processing message
            await bot.send_message(
                chat_id=task['chat_id'],
                text="🔍 Analisi in corso... Questo potrebbe richiedere alcuni secondi."
            )
            
            # Initialize processors
            scraper = ProductScraper()
            ml_processor = MLProcessor()
            
            try:
                # Step 1: Scrape product data
                product_data = await scraper.extract_product(task['url'])
                
                # Step 2: Process reviews with ML
                reviews = [{'review': r} for r in product_data.get('reviews', [])]
                sentiment_data = await ml_processor.analyze_sentiment(reviews)
                pros_cons = await ml_processor.extract_pros_cons(reviews, product_data)
                
                # Step 3: Compile results
                result = {
                    'summary': f"Product: {product_data['title']}\nPrice: {product_data['price']}\nSentiment: {sentiment_data['average_sentiment']}/5",
                    'pros_cons': pros_cons
                }
                
                # Send the result back to the user
                await bot.send_message(
                    chat_id=task['chat_id'],
                    text=f"✅ *Analisi completata*\n\n{result['summary']}",
                    parse_mode='Markdown'
                )
                
                # Send detailed analysis
                pros_cons_text = "*Pros:*\n"
                for pro in result['pros_cons']['pros']:
                    pros_cons_text += f"✓ {pro}\n"
                
                pros_cons_text += "\n*Cons:*\n"
                for con in result['pros_cons']['cons']:
                    pros_cons_text += f"✗ {con}\n"
                
                await bot.send_message(
                    chat_id=task['chat_id'],
                    text=pros_cons_text,
                    parse_mode='Markdown'
                )
                
            except Exception as analysis_error:
                logger.error(f"Analysis error: {analysis_error}")
                await bot.send_message(
                    chat_id=task['chat_id'],
                    text="Mi dispiace, si è verificato un errore durante l'analisi del prodotto."
                )
        
        elif task['task_type'] == 'product_search':
            # Import scraper
            from api.scraper import ProductScraper
            
            # Send processing message
            await bot.send_message(
                chat_id=task['chat_id'],
                text="🔍 Ricerca prodotti in corso..."
            )
            
            try:
                # Initialize scraper and search
                scraper = ProductScraper()
                search_results = await scraper.search_products(task['query'])
                
                if search_results:
                    # Format results message
                    results_text = "*Risultati della ricerca:*\n\n"
                    for i, product in enumerate(search_results[:5], 1):
                        results_text += f"{i}. [{product['title']}]({product['url']})\n"
                        results_text += f"💰 {product['price']}\n\n"
                    
                    await bot.send_message(
                        chat_id=task['chat_id'],
                        text=results_text,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                else:
                    await bot.send_message(
                        chat_id=task['chat_id'],
                        text="Nessun prodotto trovato per la tua ricerca."
                    )
                    
            except Exception as search_error:
                logger.error(f"Search error: {search_error}")
                await bot.send_message(
                    chat_id=task['chat_id'],
                    text="Mi dispiace, si è verificato un errore durante la ricerca."
                )
        
        elif task['task_type'] == 'image_analysis':
            # Import here to avoid circular imports
            from api.image_analyzer import analyze_image
            
            # Process image analysis
            result = await analyze_image(task['image_url'])
            
            # Send the result back to the user
            await bot.send_message(
                chat_id=task['chat_id'],
                text=f"📊 *Analisi immagine completata*\n\n{result['summary']}",
                parse_mode='Markdown'
            )
        
        else:
            logger.warning(f"Unknown task type: {task['task_type']}")
            await bot.send_message(
                chat_id=task['chat_id'],
                text="Mi dispiace, non riconosco questo tipo di attività."
            )
            
    except Exception as e:
        logger.error(f"Error processing task: {e}", exc_info=True)
        # Notify user of error
        try:
            await bot.send_message(
                chat_id=task['chat_id'],
                text="Mi dispiace, si è verificato un errore durante l'elaborazione della richiesta. Riprova più tardi."
            )
        except Exception as send_error:
            logger.error(f"Failed to send error message: {send_error}")

async def main() -> None:
    """Main worker loop that processes tasks from the queue"""
    # Initialize the bot
    telegram_token = os.getenv("TELEGRAM_TOKEN")
    if not telegram_token:
        logger.error("TELEGRAM_TOKEN environment variable is not set")
        return
    
    bot = Bot(token=telegram_token)
    queue = get_task_queue()
    
    logger.info("Worker started, waiting for tasks...")
    
    while True:
        try:
            # Get a task from the queue (blocking operation)
            task = await queue.dequeue()
            logger.info(f"Received task: {task['task_type']}")
            
            # Process the task
            await process_task(task, bot)
            
        except Exception as e:
            logger.error(f"Error in worker loop: {e}", exc_info=True)
            # Brief pause to prevent tight loop in case of persistent errors
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())