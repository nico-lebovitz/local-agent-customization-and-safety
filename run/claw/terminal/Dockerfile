FROM node:24-slim AS openclaw_build
RUN apt-get update && apt-get install -y --no-install-recommends python3 iproute2 iptables nftables ca-certificates && rm -rf /var/lib/apt/lists/*
RUN npm install -g openclaw@2026.9.7 --omit=dev && npm cache clean --force
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 iptables nftables ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=openclaw_build /usr/local/bin/node /usr/local/bin/node
COPY --from=openclaw_build /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/openclaw/openclaw.mjs /usr/local/bin/openclaw
RUN groupadd -g 1500 sandbox && useradd -m -u 1500 -g 1500 sandbox
WORKDIR /opt/workshop
COPY course/common.py /opt/workshop/course/common.py
COPY course/__init__.py /opt/workshop/course/__init__.py
COPY train/scripts/jisr_rules.py /opt/workshop/train/scripts/jisr_rules.py
COPY run/workshop/workshop_agent/contracts.py /opt/workshop/run/workshop/workshop_agent/contracts.py
COPY run/chain/descriptions /opt/workshop/run/chain/descriptions
COPY run/claw/terminal /opt/workshop/run/claw/terminal
RUN mkdir -p /home/sandbox/.openclaw && cp /opt/workshop/run/claw/terminal/openclaw.json /home/sandbox/.openclaw/openclaw.json && cp -r /opt/workshop/run/claw/terminal/workspace /home/sandbox/workspace && chown -R sandbox:sandbox /home/sandbox
ENV PYTHONPATH=/opt/workshop PYTHONDONTWRITEBYTECODE=1 COURSE_MODEL_URL=http://host.openshell.internal:8002
USER sandbox
CMD ["sleep","infinity"]
