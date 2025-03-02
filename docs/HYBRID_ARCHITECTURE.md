# Hybrid Architecture for Scalable Telegram Bots

## Overview

This document outlines the hybrid architecture approach for the WorthIt! Telegram bot, combining the benefits of webhooks for immediate responses with background workers for intensive tasks. This architecture is designed to be scalable, responsive, and cost-effective.

## Architecture Components

### 1. Webhook Handler (Serverless)

**Purpose:** Handle immediate user interactions and simple commands

**Implementation:**
- Deployed on Vercel (serverless)
- Responds quickly to user messages
- Delegates complex tasks to background workers
- Returns immediate acknowledgments to users

### 2. Background Worker (Long-running)

**Purpose:** Process intensive tasks like product analysis, ML inference, and web scraping

**Implementation:**
- Runs as a separate service
- Processes tasks from a queue
- Handles long-running operations
- Updates users when processing completes

### 3. Message Queue

**Purpose:** Decouple the webhook handler from the background worker

**Implementation Options:**
- **Simple:** Redis-based queue
- **Managed:** AWS SQS, Google Cloud Pub/Sub, or Azure Service Bus
- **Self-hosted:** RabbitMQ or Apache Kafka

## Implementation Guide

### Step 1: Configure the Webhook Handler

The webhook handler is already implemented in `bot/webhook_handler.py`. Ensure it:

1. Quickly acknowledges user requests
2. Enqueues complex tasks for background processing
3. Returns appropriate responses to users

```python
# Example of enqueueing a task in webhook_handler.py
async def handle_product_url(update: Update, url: str):
    # Send immediate acknowledgment
    message = await update.message.reply_text(
        "Sto analizzando il prodotto... Riceverai presto i risultati! ⏳"
    )
    
    # Enqueue the task for background processing
    await enqueue_task({
        'task_type': 'product_analysis',
        'url': url,
        'chat_id': update.effective_chat.id,
        'message_id': message.message_id
    })
```

### Step 2: Implement the Background Worker

Create a new file `worker/worker.py` that:

1. Connects to the message queue
2. Processes tasks from the queue
3. Sends results back to users via the Telegram API

### Step 3: Set Up the Message Queue

Choose a message queue solution based on your scaling needs:

- **Development:** Redis (simple setup)
- **Production:** AWS SQS or similar managed service

### Step 4: Deploy Both Components

1. Deploy the webhook handler on Vercel
2. Deploy the background worker on a suitable platform:
   - Virtual machine (DigitalOcean, AWS EC2)
   - Container service (AWS ECS, Google Cloud Run)
   - Kubernetes cluster

## Scaling Considerations

### Webhook Handler Scaling

- Automatically scales with Vercel's serverless platform
- No manual scaling needed
- Cost-effective for variable loads

### Background Worker Scaling

- Horizontal scaling: Add more worker instances
- Vertical scaling: Increase resources per worker
- Auto-scaling based on queue depth

## Monitoring and Reliability

1. Implement health checks for both components
2. Set up monitoring for queue depth and processing times
3. Implement retry logic for failed tasks
4. Add dead-letter queues for unprocessable messages

## Example Implementation

### Queue Interface

```python
# worker/queue.py
import redis
import json
import os
from typing import Dict, Any

class TaskQueue:
    def __init__(self):
        self.redis = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379'))
        self.queue_name = 'worthit_tasks'
    
    async def enqueue(self, task: Dict[str, Any]) -> bool:
        """Add a task to the queue"""
        return self.redis.lpush(self.queue_name, json.dumps(task))
    
    async def dequeue(self) -> Dict[str, Any]:
        """Get a task from the queue, blocking if empty"""
        _, task_json = self.redis.brpop(self.queue_name)
        return json.loads(task_json)
```

### Worker Implementation

```python
# worker/worker.py
import asyncio
import os
from telegram import Bot
from queue import TaskQueue
from api.main import analyze_product

async def process_task(task, bot):
    """Process a single task"""
    try:
        if task['task_type'] == 'product_analysis':
            # Perform the analysis
            result = await analyze_product(task['url'])
            
            # Send the result back to the user
            await bot.send_message(
                chat_id=task['chat_id'],
                text=f"Ecco l'analisi del prodotto:\n\n{result['summary']}",
                parse_mode='Markdown'
            )
    except Exception as e:
        print(f"Error processing task: {e}")
        # Notify user of error
        await bot.send_message(
            chat_id=task['chat_id'],
            text="Mi dispiace, si è verificato un errore durante l'analisi del prodotto."
        )

async def main():
    """Main worker loop"""
    queue = TaskQueue()
    bot = Bot(token=os.getenv('TELEGRAM_TOKEN'))
    
    print("Worker started, waiting for tasks...")
    
    while True:
        try:
            task = await queue.dequeue()
            await process_task(task, bot)
        except Exception as e:
            print(f"Error in worker loop: {e}")
            # Brief pause to prevent tight loop in case of persistent errors
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
```

## Conclusion

This hybrid architecture provides the best of both worlds:

1. **Responsiveness:** Users get immediate feedback via webhooks
2. **Scalability:** Complex tasks are handled by dedicated workers
3. **Cost-effectiveness:** Serverless for spiky traffic, dedicated resources for intensive tasks
4. **Reliability:** Decoupled components with proper error handling

Implement this architecture to ensure your Telegram bot remains responsive even as user numbers grow and processing requirements increase.