terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}

provider "docker" {}

# The monitoring stack this extension's resume claim refers to: Prometheus scraping the
# llm_monitor service's /metrics endpoint, and Grafana with that Prometheus instance
# provisioned as a datasource, both declared here rather than clicked together by hand.
# The 18-of-20 and median-detection-time numbers in the README come from
# llm_monitor/simulate.py's deterministic evaluator, not from watching this stack over real
# wall-clock hours; this stack is the infrastructure-as-code half of the claim, see Honest
# framing.

resource "local_file" "prometheus_config" {
  filename = "${path.module}/generated/prometheus.yml"
  content = yamlencode({
    global = {
      scrape_interval = "15s"
    }
    rule_files = ["/etc/prometheus/llm_monitor_rules.yml"]
    scrape_configs = [
      {
        job_name = "llm-monitor"
        static_configs = [
          { targets = ["host.docker.internal:9108"] }
        ]
      }
    ]
  })
}

# The written objectives themselves, as real PromQL: the same multi-window multi-burn-rate
# shape llm_monitor/burnrate_window.py implements in Python, expressed as Prometheus alerting
# rules against the llm_monitor_requests_total / llm_monitor_ungrounded_requests_total counters
# the service exposes. This is the infrastructure-as-code artifact the claim refers to; the
# measured 18-of-20 catch rate comes from the Python evaluator run offline (see Honest framing),
# not from these rules firing over real wall-clock hours.
resource "local_file" "prometheus_rules" {
  filename = "${path.module}/generated/llm_monitor_rules.yml"
  content = yamlencode({
    groups = [
      {
        name = "llm-monitor-groundedness-slo"
        rules = [
          {
            alert = "GroundednessFastBurn"
            expr  = "(increase(llm_monitor_ungrounded_requests_total[50s]) / increase(llm_monitor_requests_total[50s])) / 0.03 >= 14.4 and (increase(llm_monitor_ungrounded_requests_total[10m]) / increase(llm_monitor_requests_total[10m])) / 0.03 >= 14.4"
            for   = "0m"
            labels = { severity = "page", tier = "fast" }
            annotations = { summary = "Groundedness error budget burning at 14.4x or more (fast tier)" }
          },
          {
            alert = "GroundednessSlowBurn"
            expr  = "(increase(llm_monitor_ungrounded_requests_total[5m]) / increase(llm_monitor_requests_total[5m])) / 0.03 >= 6.0 and (increase(llm_monitor_ungrounded_requests_total[1h]) / increase(llm_monitor_requests_total[1h])) / 0.03 >= 6.0"
            for   = "0m"
            labels = { severity = "page", tier = "slow" }
            annotations = { summary = "Groundedness error budget burning at 6x or more (slow tier)" }
          },
          {
            alert = "LatencyP99OverBudget"
            expr  = "histogram_quantile(0.99, rate(llm_monitor_latency_ms_bucket[1h])) > 800"
            for   = "5m"
            labels = { severity = "page" }
            annotations = { summary = "p99 end-to-end latency over the 800ms budget" }
          },
          {
            alert = "CostPerRequestOverBudget"
            expr  = "(rate(llm_monitor_cost_usd_sum[1h]) / rate(llm_monitor_requests_total[1h])) > 0.02"
            for   = "5m"
            labels = { severity = "page" }
            annotations = { summary = "Mean cost per request over the $0.02 budget" }
          },
        ]
      }
    ]
  })
}

resource "local_file" "grafana_datasource" {
  filename = "${path.module}/generated/grafana-datasource.yml"
  content = yamlencode({
    apiVersion = 1
    datasources = [
      {
        name      = "Prometheus"
        type      = "prometheus"
        access    = "proxy"
        url       = "http://prometheus:9090"
        isDefault = true
      }
    ]
  })
}

resource "docker_image" "prometheus" {
  name = "prom/prometheus:v2.53.0"
}

resource "docker_image" "grafana" {
  name = "grafana/grafana:11.1.0"
}

resource "docker_network" "monitoring" {
  name = "llm-monitor-network"
}

resource "docker_container" "prometheus" {
  name  = "llm-monitor-prometheus"
  image = docker_image.prometheus.image_id
  networks_advanced {
    name = docker_network.monitoring.name
  }
  ports {
    internal = 9090
    external = 9191
  }
  volumes {
    host_path      = abspath(local_file.prometheus_config.filename)
    container_path = "/etc/prometheus/prometheus.yml"
    read_only      = true
  }
  volumes {
    host_path      = abspath(local_file.prometheus_rules.filename)
    container_path = "/etc/prometheus/llm_monitor_rules.yml"
    read_only      = true
  }
}

resource "docker_container" "grafana" {
  name  = "llm-monitor-grafana"
  image = docker_image.grafana.image_id
  networks_advanced {
    name = docker_network.monitoring.name
  }
  ports {
    internal = 3000
    external = 3001
  }
  volumes {
    host_path      = abspath(local_file.grafana_datasource.filename)
    container_path = "/etc/grafana/provisioning/datasources/prometheus.yml"
    read_only      = true
  }
  env = ["GF_SECURITY_ADMIN_PASSWORD=admin"]
}

output "prometheus_url" {
  value = "http://localhost:9191"
}

output "grafana_url" {
  value = "http://localhost:3001"
}
