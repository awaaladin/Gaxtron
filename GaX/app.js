// Simple SPA logic for wallet UI
const mainContent = document.getElementById('mainContent');
const dashboardBtn = document.getElementById('dashboardBtn');
const transactionsBtn = document.getElementById('transactionsBtn');
const logoutBtn = document.getElementById('logoutBtn');

let jwtToken = null;

function renderDashboard() {
    mainContent.innerHTML = `
        <div class="card">
            <h2>Wallet Balance</h2>
            <p id="balance">Loading...</p>
        </div>
        <div class="card">
            <h2>Send Crypto</h2>
            <form id="sendForm">
                <input type="text" id="recipient" placeholder="Recipient Address" required />
                <input type="number" id="amount" placeholder="Amount" min="0" step="any" required />
                <select id="currency">
                    <option value="BTC">Bitcoin (BTC)</option>
                    <option value="ETH">Ethereum (ETH)</option>
                </select>
                <button class="primary" type="submit">Send</button>
            </form>
            <div id="sendStatus"></div>
        </div>
    `;
    fetchBalance();
    document.getElementById('sendForm').onsubmit = sendCrypto;
}

function renderTransactions() {
    mainContent.innerHTML = `
        <div class="card">
            <h2>Transaction History</h2>
            <ul id="txList">Loading...</ul>
        </div>
    `;
    fetchTransactions();
}

function renderLogin() {
    mainContent.innerHTML = `
        <div class="card">
            <h2>Login</h2>
            <form id="loginForm">
                <input type="text" id="loginUsername" placeholder="Username" required />
                <input type="password" id="loginPassword" placeholder="Password" required />
                <button class="primary" type="submit">Login</button>
            </form>
            <p>Don't have an account? <a href="#" id="showRegister">Register</a></p>
            <div id="loginStatus"></div>
        </div>
    `;
    document.getElementById('loginForm').onsubmit = loginUser;
    document.getElementById('showRegister').onclick = renderRegister;
}

function renderRegister() {
    mainContent.innerHTML = `
        <div class="card">
            <h2>Register</h2>
            <form id="registerForm">
                <input type="text" id="registerUsername" placeholder="Username" required />
                <input type="password" id="registerPassword" placeholder="Password" required />
                <button class="primary" type="submit">Register</button>
            </form>
            <p>Already have an account? <a href="#" id="showLogin">Login</a></p>
            <div id="registerStatus"></div>
        </div>
    `;
    document.getElementById('registerForm').onsubmit = registerUser;
    document.getElementById('showLogin').onclick = renderLogin;
}

function loginUser(e) {
    e.preventDefault();
    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;
    document.getElementById('loginStatus').textContent = 'Logging in...';
    fetch('/api/auth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`
    })
    .then(res => res.json())
    .then(data => {
        if (data.access_token) {
            jwtToken = data.access_token;
            renderDashboard();
        } else {
            document.getElementById('loginStatus').textContent = 'Login failed.';
        }
    })
    .catch(() => {
        document.getElementById('loginStatus').textContent = 'Error logging in.';
    });
}

function registerUser(e) {
    e.preventDefault();
    const username = document.getElementById('registerUsername').value;
    const password = document.getElementById('registerPassword').value;
    document.getElementById('registerStatus').textContent = 'Registering...';
    fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
    })
    .then(res => res.json())
    .then(data => {
        if (data.access_token) {
            jwtToken = data.access_token;
            renderDashboard();
        } else {
            document.getElementById('registerStatus').textContent = 'Registration failed.';
        }
    })
    .catch(() => {
        document.getElementById('registerStatus').textContent = 'Error registering.';
    });
}

function logoutUser() {
    jwtToken = null;
    renderLogin();
}

function fetchBalance() {
    fetch('/api/wallet/balance', {
        headers: jwtToken ? { 'Authorization': 'Bearer ' + jwtToken } : {}
    })
        .then(res => res.json())
        .then(data => {
            document.getElementById('balance').textContent = `${data.btc} BTC | ${data.eth} ETH | ${data.usdt} USDT`;
        })
        .catch(() => {
            document.getElementById('balance').textContent = 'Error loading balance';
        });
}

function fetchTransactions() {
    fetch('/api/wallet/transactions', {
        headers: jwtToken ? { 'Authorization': 'Bearer ' + jwtToken } : {}
    })
        .then(res => res.json())
        .then(data => {
            document.getElementById('txList').innerHTML = data.map(tx =>
                `<li>${tx.type === 'send' ? 'Sent' : 'Received'} ${tx.amount} ${tx.currency} to/from ${tx.address} on ${tx.timestamp}</li>`
            ).join('');
        })
        .catch(() => {
            document.getElementById('txList').innerHTML = '<li>Error loading transactions</li>';
        });
}

function sendCrypto(e) {
    e.preventDefault();
    const recipient = document.getElementById('recipient').value;
    const amount = document.getElementById('amount').value;
    const currency = document.getElementById('currency').value;
    document.getElementById('sendStatus').textContent = 'Sending...';
    fetch('/api/wallet/send', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...(jwtToken ? { 'Authorization': 'Bearer ' + jwtToken } : {})
        },
        body: JSON.stringify({ recipient, amount: parseFloat(amount), currency, address: recipient })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            document.getElementById('sendStatus').textContent = `Sent ${amount} ${currency} to ${recipient}!`;
            fetchBalance();
            fetchTransactions();
        } else {
            document.getElementById('sendStatus').textContent = data.message;
        }
    })
    .catch(() => {
        document.getElementById('sendStatus').textContent = 'Error sending transaction';
    });
}

// Navigation
function showDashboardIfLoggedIn() {
    if (jwtToken) {
        renderDashboard();
    } else {
        renderLogin();
    }
}
dashboardBtn.onclick = showDashboardIfLoggedIn;
transactionsBtn.onclick = function() {
    if (jwtToken) {
        renderTransactions();
    } else {
        renderLogin();
    }
};
logoutBtn.onclick = logoutUser;

// Initial load
showDashboardIfLoggedIn();
