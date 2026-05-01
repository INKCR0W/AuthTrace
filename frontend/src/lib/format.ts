const dateTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "未记录";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return dateTimeFormatter.format(date);
}

export function formatPercent(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "未记录";
  }

  return `${value}%`;
}

export function formatRemaining(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "未记录";
  }

  return String(value);
}

export function formatCount(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}

export function formatDurationMs(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "未记录";
  }

  if (value < 1000) {
    return `${value} ms`;
  }

  const seconds = value / 1000;
  if (seconds < 60) {
    return `${seconds.toFixed(1)} s`;
  }

  return `${(seconds / 60).toFixed(1)} min`;
}

export function formatMinutesSpan(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "未记录";
  }

  if (value < 60) {
    return `${value} 分钟`;
  }

  const hours = Math.floor(value / 60);
  const minutes = value % 60;
  if (minutes === 0) {
    return `${hours} 小时`;
  }

  return `${hours} 小时 ${minutes} 分钟`;
}

export function formatStatusCode(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "未探测";
  }

  return String(value);
}

export function toBooleanQuery(value: string) {
  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }
  return undefined;
}
