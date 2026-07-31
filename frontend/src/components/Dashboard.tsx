import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";

interface DashboardProperty {
  id: string;
  name: string;
  timezone: string;
  latest_period: string | null;
}

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<DashboardProperty[]>([]);
  const [selectedProperty, setSelectedProperty] = useState("");
  const [selectedPeriod, setSelectedPeriod] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    const fetchProperties = async () => {
      setLoading(true);
      setError("");

      try {
        const tenantProperties = await SecureAPI.getDashboardProperties();
        if (cancelled) return;

        setProperties(tenantProperties);
        setSelectedProperty(tenantProperties[0]?.id ?? "");
        setSelectedPeriod(
          tenantProperties.find((property) => property.latest_period)?.latest_period ?? ""
        );
      } catch (err) {
        if (cancelled) return;
        console.error("Failed to load dashboard properties", err);
        setError("We couldn't load your properties. Please try again.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchProperties();

    return () => {
      cancelled = true;
    };
  }, []);

  const renderRevenueContent = () => {
    if (loading) {
      return (
        <div className="rounded-xl border border-gray-200 bg-white p-6" role="status">
          <div className="animate-pulse space-y-4">
            <div className="h-4 w-1/4 rounded bg-gray-100" />
            <div className="h-8 w-1/2 rounded bg-gray-100" />
          </div>
          <span className="sr-only">Loading properties</span>
        </div>
      );
    }

    if (error) {
      return (
        <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700" role="alert">
          {error}
        </div>
      );
    }

    if (properties.length === 0) {
      return (
        <div className="rounded-lg bg-gray-50 p-6 text-sm text-gray-600">
          No properties are available for this account.
        </div>
      );
    }

    return (
      <RevenueSummary
        key={`${selectedProperty}:${selectedPeriod}`}
        propertyId={selectedProperty}
        period={selectedPeriod || undefined}
      />
    );
  };

  return (
    <div className="p-4 lg:p-6 min-h-full">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-6 text-gray-900">Property Management Dashboard</h1>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 lg:p-6">
          <div className="mb-6">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4">
              <div>
                <h2 className="text-lg lg:text-xl font-medium text-gray-900 mb-2">Revenue Overview</h2>
                <p className="text-sm lg:text-base text-gray-600">
                  Monthly performance insights for your properties
                </p>
              </div>

              {!loading && !error && properties.length > 0 && (
                <div className="grid w-full gap-3 sm:w-auto sm:grid-cols-2">
                  <div className="flex flex-col">
                    <label htmlFor="dashboard-property" className="mb-1 text-xs font-medium text-gray-700">
                      Select Property
                    </label>
                    <select
                      id="dashboard-property"
                      value={selectedProperty}
                      onChange={(event) => setSelectedProperty(event.target.value)}
                      className="block w-full min-w-[200px] rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500"
                    >
                      {properties.map((property) => (
                        <option key={property.id} value={property.id}>
                          {property.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="flex flex-col">
                    <label htmlFor="dashboard-period" className="mb-1 text-xs font-medium text-gray-700">
                      Reporting Month
                    </label>
                    <input
                      id="dashboard-period"
                      type="month"
                      value={selectedPeriod}
                      onChange={(event) => setSelectedPeriod(event.target.value)}
                      className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500"
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="space-y-6">
            {renderRevenueContent()}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
