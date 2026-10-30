FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 iptables nftables ca-certificates && rm -rf /var/lib/apt/lists/*
RUN groupadd -g 1000 sandbox && useradd -m -u 1000 -g 1000 sandbox
WORKDIR /opt
COPY course /opt/course
COPY train/scripts/jisr_rules.py /opt/train/scripts/jisr_rules.py
COPY run/workshop/workshop_agent/contracts.py /opt/run/workshop/workshop_agent/contracts.py
COPY run/chain/descriptions /opt/run/chain/descriptions
RUN chown sandbox:sandbox /opt/course/openshell/canary.txt
ENV PYTHONPATH=/opt PYTHONDONTWRITEBYTECODE=1 COURSE_MODEL_URL=http://host.openshell.internal:8002
USER sandbox
CMD ["python3", "-m", "course.openshell.launch"]
