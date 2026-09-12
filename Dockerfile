FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir streamlit python-dotenv apscheduler pandas-market-calendars

COPY . .

# Safe default: launch the dashboard. Cloud worker services should override
# the command with: python automation_runner.py
CMD ["python", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
