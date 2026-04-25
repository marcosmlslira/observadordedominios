set -e
for svc in observador_backend observador_czds_ingestor observador_ct_ingestor observador_similarity_worker observador_openintel_ingestor observador_health_worker observador_scan_worker observador_enrichment_worker observador_assessment_worker; do
  echo "=== updating $svc ==="
  docker service update --image observador-backend:homographfix-20260418-1 --no-resolve-image --force "$svc"
done
