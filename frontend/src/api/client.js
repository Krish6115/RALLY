const API_URL = "http://localhost:8000/api";

export async function getOverview() {
    const res = await fetch(`${API_URL}/overview`);
    if (!res.ok) throw new Error("Failed to fetch overview");
    return res.json();
}

export async function getFeed() {
    const res = await fetch(`${API_URL}/feed`);
    if (!res.ok) throw new Error("Failed to fetch feed");
    return res.json();
}

export async function getDecision(paymentId) {
    const res = await fetch(`${API_URL}/decision/${paymentId}`);
    if (!res.ok) throw new Error("Failed to fetch decision");
    return res.json();
}

export async function getEvaluation() {
    const res = await fetch(`${API_URL}/evaluation`);
    if (!res.ok) throw new Error("Failed to fetch evaluation");
    return res.json();
}

export async function simulateScenario(scenario) {
    const res = await fetch(`${API_URL}/simulate/failure`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ scenario })
    });
    if (!res.ok) throw new Error("Failed to simulate");
    return res.json();
}
