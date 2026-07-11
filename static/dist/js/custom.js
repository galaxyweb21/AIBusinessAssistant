function openCheckoutModal(id) {
    document.getElementById("booking_id").value = id;

    fetch(`/hotels/late-fee-preview/${id}/`)
    .then(res => res.json())
    .then(data => {
        document.getElementById("guestName").innerText = data.guest;
        document.getElementById("feeReason").innerText = data.reason;
        document.getElementById("feeAmount").innerText =
            "GHS " + parseFloat(data.amount || 0).toFixed(2);

        $('#lateModal').modal('show');
    })
    .catch(err => {
        console.error(err);
        alert("Error loading checkout");
    });
}