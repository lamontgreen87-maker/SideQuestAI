# RunPod Serverless Deployment Guide

## Overview

This guide sets up a **serverless 72B endpoint** for instant task shattering with no cold start delays.

**Benefits**:
- ⚡ **Instant response**: 30 seconds vs 6.5 minutes
- 💰 **Pay per use**: $0.0125 per shatter vs $0.15
- 🔄 **Auto-scaling**: No manual start/stop
- 🎯 **Warm workers**: Always ready for inference

---

## Prerequisites

- RunPod account with credits
- Docker image: `lamontnelson12/hive-brain:latest` (already built)
- RunPod API key in `.env`

---

## Step 1: Create Serverless Endpoint

### Via RunPod Web UI

1. **Navigate to Serverless**
   - Go to https://www.runpod.io/console/serverless
   - Click **"New Endpoint"**

2. **Configure Endpoint**
   ```
   Name: hive-brain-72b-serverless
   GPU Type: RTX 4090 (or A6000)
   Container Image: lamontnelson12/hive-brain:latest
   Container Start Command: (leave default)
   ```

3. **Set Environment Variables**
   ```
   MODEL_NAME=Qwen/Qwen2.5-72B-Instruct-AWQ
   TENSOR_PARALLEL_SIZE=2
   GPU_MEMORY_UTILIZATION=0.95
   MAX_MODEL_LEN=8192
   ```

4. **Configure Scaling**
   ```
   Min Workers: 0
   Max Workers: 3
   Idle Timeout: 5 seconds
   
   ✅ Enable "Active Workers" (warm pool)
   Active Workers: 1  ← This keeps 1 worker always warm
   ```

5. **Advanced Settings**
   ```
   Max Concurrent Requests: 10
   Execution Timeout: 300 seconds
   ```

6. **Click "Deploy"**

---

## Step 2: Get Endpoint Details

After deployment, you'll see:

```
Endpoint ID: abc123def456
Endpoint URL: https://api.runpod.ai/v2/abc123def456
API Key: (use your existing RUNPOD_API_KEY)
```

**Save these to your `.env` file**:
```bash
RUNPOD_SERVERLESS_ENDPOINT_ID=abc123def456
RUNPOD_SERVERLESS_URL=https://api.runpod.ai/v2/abc123def456
```

---

## Step 3: Test Endpoint

Use the test script:

```bash
python test_serverless.py
```

Expected output:
```
✅ Serverless endpoint is ready!
Response time: 2.3 seconds
Model: Qwen2.5-72B-Instruct-AWQ
```

---

## Step 4: Update Orchestrator

The orchestrator is already updated to support serverless. Just set the environment variable:

```bash
# In .env
RUNPOD_MODE=serverless  # Use serverless endpoint
# RUNPOD_MODE=persistent  # Use persistent pod (old way)
```

---

## API Usage

### Request Format

```python
import requests

response = requests.post(
    f"{RUNPOD_SERVERLESS_URL}/run",
    headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
    json={
        "input": {
            "prompt": "Your prompt here",
            "max_tokens": 500,
            "temperature": 0.7
        }
    }
)

result = response.json()
```

### Response Format

```json
{
  "id": "request-id",
  "status": "COMPLETED",
  "output": {
    "text": "Generated response...",
    "tokens": 245
  }
}
```

---

## Cost Breakdown

### Serverless Pricing

**GPU**: RTX 4090 @ $0.00036/sec = $1.30/hr
**With 2 GPUs** (tensor parallel): $2.60/hr

**Per Shatter**:
- Inference time: ~30 seconds
- Cost: 30 sec × $2.60/hr ÷ 3600 = **$0.022**

**Warm Pool** (1 active worker):
- Idle cost: $2.60/hr × 1 worker = **$2.60/hr**
- Daily: $62.40/day

### Cost Comparison

| Scenario | Persistent Pod | Serverless (warm) |
|----------|---------------|-------------------|
| **1 shatter/day** | $0.15 | $62.42 |
| **10 shatters/day** | $1.50 | $62.62 |
| **100 shatters/day** | $15.00 | $64.80 |

> **Note**: Serverless is only cost-effective at **high volume** (>100 shatters/day) OR if you value instant response time.

### Alternative: No Warm Pool

If you disable warm workers:
- **Cold start**: ~60 seconds (faster than persistent pod's 6 min)
- **Cost per shatter**: $0.045 (60 sec inference)
- **No idle costs**: $0/hr when not in use

**Recommended for low-volume usage** (<10 shatters/day)

---

## Configuration Options

### Option A: Warm Pool (Instant Response)
```
Active Workers: 1
Idle Timeout: 5 seconds
Cost: $2.60/hr idle + $0.022/shatter
Response Time: 30 seconds
```

### Option B: Cold Start (Budget)
```
Active Workers: 0
Idle Timeout: 5 seconds
Cost: $0/hr idle + $0.045/shatter
Response Time: 90 seconds (60s cold start + 30s inference)
```

### Option C: Hybrid (Recommended)
```
Active Workers: 0
Min Workers: 0
Max Workers: 3
Cost: $0/hr idle + $0.045/shatter
Response Time: 90 seconds first request, 30 seconds subsequent
```

---

## Monitoring

### Check Endpoint Status

```bash
python status_serverless.py
```

### View Logs

1. Go to RunPod Console → Serverless
2. Click your endpoint
3. View "Logs" tab

### Cost Tracking

RunPod dashboard shows:
- Total requests
- Total compute time
- Current spend

---

## Troubleshooting

### Endpoint Not Responding

```bash
# Check endpoint health
curl https://api.runpod.ai/v2/{ENDPOINT_ID}/health
```

### Cold Start Too Slow

- Increase "Active Workers" to 1
- Or use larger GPU (A6000 loads faster)

### Out of Memory

- Reduce `MAX_MODEL_LEN` to 4096
- Or use A100 (80GB VRAM)

---

## Next Steps

1. ✅ Create serverless endpoint (when funded)
2. ✅ Test with `test_serverless.py`
3. ✅ Set `RUNPOD_MODE=serverless` in `.env`
4. ✅ Monitor costs for first week
5. ✅ Adjust warm pool based on usage

---

## Rollback to Persistent Pod

If you need to go back:

```bash
# In .env
RUNPOD_MODE=persistent
```

Then use `start_brain.py` / `stop_brain.py` as before.
