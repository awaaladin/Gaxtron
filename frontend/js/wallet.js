/**
 * MetaMask wallet helpers — Sepolia only. No private keys; signing stays in the wallet.
 */
(function (global) {
  const SEPOLIA_CHAIN_ID = '0xaa36a7';

  const SEPOLIA_CHAIN_PARAMS = {
    chainId: SEPOLIA_CHAIN_ID,
    chainName: 'Sepolia',
    nativeCurrency: { name: 'Sepolia ETH', symbol: 'ETH', decimals: 18 },
    rpcUrls: ['https://rpc.sepolia.org'],
    blockExplorerUrls: ['https://sepolia.etherscan.io'],
  };

  function hasProvider() {
    return typeof global.ethereum !== 'undefined';
  }

  function ethToWeiHex(amountEth) {
    const parts = String(amountEth).split('.');
    const whole = BigInt(parts[0] || '0');
    const frac = (parts[1] || '').padEnd(18, '0').slice(0, 18);
    const wei = whole * BigInt('1000000000000000000') + BigInt(frac);
    return '0x' + wei.toString(16);
  }

  async function ensureSepolia() {
    if (!hasProvider()) return false;
    try {
      await global.ethereum.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: SEPOLIA_CHAIN_ID }],
      });
      return true;
    } catch (err) {
      if (err && err.code === 4902) {
        await global.ethereum.request({
          method: 'wallet_addEthereumChain',
          params: [SEPOLIA_CHAIN_PARAMS],
        });
        return true;
      }
      throw err;
    }
  }

  async function connectWallet() {
    if (!hasProvider()) {
      throw new Error('MetaMask is not installed. Use the QR code or copy the address instead.');
    }
    await ensureSepolia();
    const accounts = await global.ethereum.request({ method: 'eth_requestAccounts' });
    return accounts[0] || null;
  }

  async function sendPayment(to, amountEth, fromAddress) {
    if (!hasProvider()) {
      throw new Error('MetaMask is not available');
    }
    await ensureSepolia();
    const accounts = await global.ethereum.request({ method: 'eth_requestAccounts' });
    const from = fromAddress || accounts[0];
    if (!from) throw new Error('No wallet account selected');

    const txHash = await global.ethereum.request({
      method: 'eth_sendTransaction',
      params: [{
        from,
        to,
        value: ethToWeiHex(amountEth),
        chainId: SEPOLIA_CHAIN_ID,
      }],
    });
    return txHash;
  }

  global.GaxtronWallet = {
    hasProvider,
    connectWallet,
    sendPayment,
    ensureSepolia,
    ethToWeiHex,
    SEPOLIA_CHAIN_ID,
  };
})(window);
