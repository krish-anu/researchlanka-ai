FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt pyproject.toml README.md ./
COPY research_analytics ./research_analytics
COPY src ./src
COPY configurations ./configurations
COPY examples ./examples

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["python", "-m", "research_analytics.cli"]
CMD ["run-all", "--config", "configurations/example_country/config.json"]
