export function overBudget(actualBytes, maxKb) {
  return actualBytes > maxKb * 1024;
}

export function formatKb(bytes) {
  return (bytes / 1024).toFixed(1) + "kb";
}
