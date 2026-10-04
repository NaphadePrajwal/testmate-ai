import { useCallback, useEffect, useState } from "react";

interface ApiResource<T> {
  data: T | null;
  error: string | null;
  isLoading: boolean;
  reload: () => Promise<void>;
}

export function useApiResource<T>(loader: () => Promise<T>): ApiResource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const reload = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setData(await loader());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "An unexpected error occurred.");
    } finally {
      setIsLoading(false);
    }
  }, [loader]);

  useEffect(() => {
    queueMicrotask(() => void reload());
  }, [reload]);

  return { data, error, isLoading, reload };
}
