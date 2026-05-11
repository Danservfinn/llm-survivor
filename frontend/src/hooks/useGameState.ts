"use client";

import { useState, useEffect } from 'react';
import { ApiStateResponse } from '@/types';
import { apiUrl } from '@/lib/api';

export function useGameState() {
  const [data, setData] = useState<ApiStateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch(apiUrl('/api/state'));
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const jsonData = await response.json();
        setData(jsonData);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch game state:', err);
        setError(err instanceof Error ? err.message : 'Unknown error');
        // Silently retain previous state on error
      }
    };

    // Initial fetch
    fetchData();

    // Poll every 5 seconds
    const intervalId = setInterval(fetchData, 5000);

    return () => clearInterval(intervalId);
  }, []);

  return { data, error };
}
