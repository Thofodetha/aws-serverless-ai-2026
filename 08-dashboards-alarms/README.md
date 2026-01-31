# Week 8: CloudWatch Dashboards & Alarms

## What We Built

### CloudWatch Dashboard: AI-Assistant-Dashboard
- **Widget 1:** RequestCount by model (Number widget)
- **Widget 2:** EstimatedCost by model (Number widget)
- **Widget 3:** BedrockDuration - Average response time (Number widget)

**Dashboard URL:** Available in AWS CloudWatch Console

### CloudWatch Alarm: Daily-Cost-Exceeds-1-Dollar
- **Metric:** AIAssistant > EstimatedCost (nova-lite)
- **Statistic:** Sum
- **Period:** 1 day
- **Threshold:** Greater than $1
- **Action:** Send notification to SNS topic `ai-assistant-alerts`
- **Status:** Active and email confirmed

### SNS Topic
- **Name:** ai-assistant-alerts
- **Subscription:** Email (confirmed)
- **Purpose:** Send alerts when alarms trigger

## Live Metrics Shown
- Nova Lite: 1 request, $0.000171 cost
- Nova Pro: 1 request, $0.00264 cost
- Average response time: 4.4-4.8 seconds

## How to Access
1. Go to AWS Console > CloudWatch
2. Click "Dashboards" > "AI-Assistant-Dashboard"
3. View live metrics and graphs

## Week 8 Achievements
✅ Professional visual monitoring
✅ Automated cost alerts
✅ Email notifications configured
✅ Production-ready observability
