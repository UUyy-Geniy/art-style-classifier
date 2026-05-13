#!/usr/bin/env sh
set -eu

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
bundle_dir="${MODEL_BUNDLE_DIR:-$repo_root/backend/src/artstyle_backend/ml_model/model_bundle}"
feature_store_name="${MODEL_FEATURE_STORE_NAME:-features_large_cls_mean_top18_contemporary_merged_v1.npz}"
feature_store_path="$bundle_dir/$feature_store_name"

if [ -f "$feature_store_path" ]; then
  echo "Feature store already exists: $feature_store_path"
  exit 0
fi

if [ -z "${MODEL_FEATURE_STORE_URL:-}" ]; then
  echo "MODEL_FEATURE_STORE_URL is not set."
  echo "Put $feature_store_name into $bundle_dir manually,"
  echo "or set MODEL_FEATURE_STORE_URL to a GitHub Release/S3/HuggingFace direct download URL."
  exit 2
fi

mkdir -p "$bundle_dir"
tmp_path="$feature_store_path.tmp"

echo "Downloading feature store:"
echo "  from: $MODEL_FEATURE_STORE_URL"
echo "  to:   $feature_store_path"

curl -L --fail --show-error --progress-bar "$MODEL_FEATURE_STORE_URL" -o "$tmp_path"

if [ -n "${MODEL_FEATURE_STORE_SHA256:-}" ]; then
  actual_sha="$(shasum -a 256 "$tmp_path" | awk '{print $1}')"
  if [ "$actual_sha" != "$MODEL_FEATURE_STORE_SHA256" ]; then
    rm -f "$tmp_path"
    echo "SHA256 mismatch for $feature_store_name"
    echo "  expected: $MODEL_FEATURE_STORE_SHA256"
    echo "  actual:   $actual_sha"
    exit 3
  fi
fi

mv "$tmp_path" "$feature_store_path"
echo "Downloaded: $feature_store_path"
