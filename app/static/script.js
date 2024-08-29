function toggleMenu() {
    var menu = document.getElementById("userMenu");
    menu.classList.toggle("active");
}

document.addEventListener('click', function(event) { 
    var menu = document.getElementById("userMenu");
    var profileImg = document.querySelector('.profile-img');

    // If the click was outside the menu and not on the profile image, close the menu
    if (!menu.contains(event.target) && !profileImg.contains(event.target)) {
        menu.classList.remove("active");
    }
});

// Store the last known scroll position
let lastScrollTop = 0;
const navbar = document.querySelector('.nav-g');

window.addEventListener('scroll', function() {
    let currentScroll = window.pageYOffset || document.documentElement.scrollTop;

    if (currentScroll > lastScrollTop) {
        // Scrolling down
        navbar.style.top = '-70px'; // Adjust based on your navbar height
    } else {
        // Scrolling up
        navbar.style.top = '0';
    }

    lastScrollTop = currentScroll <= 0 ? 0 : currentScroll; // For Mobile or negative scrolling
});


function displayoff(element_id, input = null){
    let error_message = document.getElementById(element_id);
    error_message.style.display = "none";

    if (element_id == "uname_err"){
        var regex = /^[a-zA-Z0-9_]*$/;
            var errorMessage = document.getElementById('error-message');

            if (!regex.test(input.value)) {
                errorMessage.textContent = "Only alphanumeric characters and underscores are allowed.";
            } else {
                errorMessage.textContent = ""; // Clear error message if input is valid
            }
    }
}

function validateForm() {
    var input = document.getElementById('username');
    var regex = /^[a-zA-Z0-9_]*$/;
    var errorMessage = document.getElementById('error-message');

    if (!regex.test(input.value)) {
        errorMessage.textContent = "Only alphanumeric characters and underscores are allowed.";
        return false; // Prevent form submission
    }

    return true; // Allow form submission
}

function flash() {
        // Get the flash message element
        var flashMessage = document.getElementById('flash-message');

        // Show the flash message
        flashMessage.classList.add('show');

        // Automatically hide the flash message after 3 seconds
        setTimeout(function() {
            flashMessage.classList.remove('show');
        }, 3000);

        // Close button functionality
        var closeButton = document.getElementById('close-btn');
        closeButton.addEventListener('click', function() {
            flashMessage.classList.remove('show');
        });
    }

    document.addEventListener("DOMContentLoaded", function() {
        const navLinks = document.querySelectorAll('.navbar-dark .nav-link');
    
        navLinks.forEach(link => {
            link.addEventListener('click', function() {
                navLinks.forEach(nav => nav.classList.remove('active'));
                this.classList.add('active');
            });
        });
    });
    