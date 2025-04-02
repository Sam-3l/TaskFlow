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

// Todos
document.addEventListener('DOMContentLoaded', () => {
    const taskId = document.getElementById('task-id').value;
    const csrfToken = document.getElementById('csrf-token').value;
    let progress = [];

    // Modal HTML template (add this to your HTML file)
    const modalHTML = `
    <div class="modal fade" id="customModal" tabindex="-1" aria-labelledby="customModalLabel" aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="customModalLabel">Notification</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body" id="customModalBody">
                    <!-- Content will be inserted here -->
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="button" class="btn btn-primary" id="customModalConfirm">Confirm</button>
                </div>
            </div>
        </div>
    </div>

    <div class="modal fade" id="promptModal" tabindex="-1" aria-labelledby="promptModalLabel" aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="promptModalLabel">Edit Todo</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <div class="mb-3">
                        <input type="text" class="form-control" id="promptInput" placeholder="Enter new text">
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="button" class="btn btn-primary" id="promptSubmit">Submit</button>
                </div>
            </div>
        </div>
    </div>
    `;

    // Add modals to the DOM if they don't exist
    if (!document.getElementById('customModal')) {
        document.body.insertAdjacentHTML('beforeend', modalHTML);
    }

    // Initialize Bootstrap modals
    const customModal = new bootstrap.Modal(document.getElementById('customModal'));
    const promptModal = new bootstrap.Modal(document.getElementById('promptModal'));

    // Show modal function
    function showModal(title, message, confirmCallback = null) {
        document.getElementById('customModalLabel').textContent = title;
        document.getElementById('customModalBody').textContent = message;
        
        const confirmBtn = document.getElementById('customModalConfirm');
        
        // Remove previous event listeners
        const newConfirmBtn = confirmBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
        
        if (confirmCallback) {
            newConfirmBtn.addEventListener('click', () => {
                confirmCallback();
                customModal.hide();
            });
        } else {
            newConfirmBtn.addEventListener('click', () => customModal.hide());
        }
        
        customModal.show();
    }

    // Show prompt function
    function showPrompt(title, defaultValue, callback) {
        document.getElementById('promptModalLabel').textContent = title;
        const promptInput = document.getElementById('promptInput');
        promptInput.value = defaultValue || '';
        
        const submitBtn = document.getElementById('promptSubmit');
        
        // Remove previous event listeners
        const newSubmitBtn = submitBtn.cloneNode(true);
        submitBtn.parentNode.replaceChild(newSubmitBtn, submitBtn);
        
        newSubmitBtn.addEventListener('click', () => {
            callback(promptInput.value);
            promptModal.hide();
        });
        
        promptModal.show();
        promptInput.focus();
    }

    // Error handling wrapper for fetch requests
    async function handleFetch(url, options, successMessage = null) {
        try {
            const response = await fetch(url, options);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('Fetch error:', error);
            showModal('Error', 'Something went wrong. Please try again later.');
            throw error; // Re-throw for additional handling if needed
        }
    }

    // Real-time Todo Interactions
    document.querySelector('.todo-list').addEventListener('click', async (e) => {
        const todoItem = e.target.closest('.todo-item');
        if (!todoItem) return;
        
        const todoId = todoItem.dataset.todoId;

        // Checkbox Toggle
        if (e.target.matches('input[type="checkbox"]')) {
            const isCompleted = e.target.checked;
            const textElement = todoItem.querySelector('.todo-text');
            
            if (isCompleted) {
                textElement.classList.add('completed');
            } else {
                textElement.classList.remove('completed');
            }
            
            let todoIndex = progress.findIndex(todo => todo.todoId === todoId);
            if (todoIndex !== -1) {
                progress.splice(todoIndex, 1);
            } else {
                progress.push({ todoId, progress: isCompleted ? 1 : -1 });
            }
            
            if (progress.length !== 0) {
                toggleProgressUI("show");
            } else {
                toggleProgressUI("hide");
            }
        }

        // Delete Todo
        if (e.target.closest('.btn-delete')) {
            const wasCompleted = todoItem.dataset.initialCompleted === 'true';
            
            const executeDelete = async () => {
                try {
                    await deleteTodo(todoId, wasCompleted);
                    location.reload();
                } catch (error) {
                    console.error('Delete error:', error);
                }
            };

            if (progress.length !== 0) {
                // Show unsaved changes warning first
                showModal('Unsaved Changes', 
                    'You have unsaved changes. Progress would be lost if you continue.', 
                    () => {
                        // Only show delete confirmation after user confirms they want to continue
                        const confirmDelete = () => {
                            showModal('Confirm Delete', 
                                'Are you sure you want to delete this todo item?', 
                                executeDelete,
                                'Delete'
                            );
                        };
                        
                        // Small timeout ensures the first modal closes completely
                        setTimeout(confirmDelete, 300);
                    }
                );
            } else {
                // No unsaved changes - go straight to delete confirmation
                showModal('Confirm Delete', 
                    'Are you sure you want to delete this todo item?', 
                    executeDelete,
                    'Delete'
                );
            }
        }

        // Edit Todo
        if (e.target.closest('.btn-edit')) {
            if (progress.length !== 0) {
                showModal('Unsaved Changes', 'You have unsaved changes. Progress would be lost if you continue.', () => {
                    const textElement = todoItem.querySelector('.todo-text');
                    showPrompt('Edit Todo', textElement.textContent, async (newText) => {
                        if (newText) {
                            try {
                                await updateTodo(todoId, { content: newText });
                                location.reload();
                            } catch (error) {
                                console.error('Update error:', error);
                            }
                        }
                    });
                });
            } else {
                const textElement = todoItem.querySelector('.todo-text');
                showPrompt('Edit Todo', textElement.textContent, async (newText) => {
                    if (newText) {
                        try {
                            await updateTodo(todoId, { content: newText });
                            location.reload();
                        } catch (error) {
                            console.error('Update error:', error);
                        }
                    }
                });
            }
        }
    });

    // Add New Todo
    document.getElementById('add-task-btn').addEventListener('click', async () => {
        const btn = document.getElementById('add-task-btn');
        btn.disabled = true;
        
        if (progress.length !== 0) {
            showModal('Unsaved Changes', 'You have unsaved changes. Progress would be lost if you continue.', async () => {
                await addNewTodo();
                btn.disabled = false;
            });
            return;
        }
        
        await addNewTodo();
        btn.disabled = false;
    });

    async function addNewTodo() {
        const input = document.getElementById('task-input');
        const content = input.value.trim();
        if (!content) return;

        try {
            await handleFetch(`/tasks/${taskId}/todos`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken 
                },
                body: JSON.stringify({ content })
            }, 'Todo added successfully!');
            
            location.reload();
        } catch (error) {
            console.error('Add todo error:', error);
        }
    }

    // Save Progress
    document.getElementById('save-progress').addEventListener('click', async () => {
        try {
            for (let index = 0; index < progress.length; index++) {
                const todo = progress[index];
                await updateTodo(todo.todoId, { is_completed: todo.progress === 1 ? true : false });            
            }
            
            progress = progress.map(todo => todo.progress);
            const notes = document.getElementById("notes").value;
            
            await handleFetch(`/tasks/${taskId}/progress`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ progress, notes: notes ? notes : null })
            }, 'Progress saved successfully!');
            
            location.reload();
        } catch (error) {
            console.error('Save progress error:', error);
        }
    });

    // Discard Changes
    document.getElementById('discard-progress').addEventListener('click', () => {
        showModal('Discard Changes', 'Are you sure you want to discard all changes?', () => {
            document.querySelectorAll('.todo-item').forEach(item => {
                const checkbox = item.querySelector('input[type="checkbox"]');
                checkbox.checked = item.dataset.initialCompleted === 'true';
                const textElement = item.querySelector('.todo-text');
                if (checkbox.checked) {
                    textElement.classList.add('completed');
                } else {
                    textElement.classList.remove('completed');
                }
            });
            progress = [];
            toggleProgressUI("hide");
        });
    });

    // Helper Functions
    function toggleProgressUI(action) {
        if (action === "show") {
            document.querySelector('.progress-actions').classList.add('visible');
        } else {
            document.querySelector('.progress-actions').classList.remove('visible');
        }
    }

    // Helper function to update a todo
    async function updateTodo(todoId, data) {
        return handleFetch(`/todos/${todoId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken  
            },
            body: JSON.stringify(data)
        });
    }

    // Helper function to delete a todo
    async function deleteTodo(todoId, wasCompleted) {
        return handleFetch(`/todos/${todoId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken  
            }
        });
    }
});

// Tasks sort
document.addEventListener('DOMContentLoaded', function() {
    const sortLabels = {
        'priority': 'Priority & Last Modified',
        'deadline': 'Deadline',
        'last_modified': 'Last Modified'
    };

    const sortKeys = {
        PRIORITY: 'priority',
        DEADLINE: 'deadline',
        LAST_MODIFIED: 'last_modified'
    };

    // Priority hierarchy
    const priorityOrder = {
        'critical': 1,
        'high-priority': 2,
        'medium-priority': 3,
        'low-priority': 4,
        'optional': 5
    };

    // Get stored sort or default to priority
    const currentSort = localStorage.getItem('taskSort') || sortKeys.PRIORITY;
    applySort(currentSort);

    // Dropdown click handler
    document.querySelectorAll('.tasks-sort .dropdown-item').forEach(item => {
        item.addEventListener('click', function() {
            const sortKey = this.dataset.sort;
            localStorage.setItem('taskSort', sortKey);
            applySort(sortKey);
        });
    });

    function applySort(sortKey) {
        const container = document.getElementById('tasks-container');
        const tasks = Array.from(container.querySelectorAll('.task-card-container'));

        tasks.sort(getSortFunction(sortKey));
        tasks.forEach(task => container.appendChild(task));
        updateActiveSortUI(sortKey);
    }

    function updateActiveSortUI(sortKey) {
        // Update dropdown label
        document.getElementById('current-sort-label').textContent = sortLabels[sortKey];
        
        // Remove all active states
        document.querySelectorAll('.tasks-sort .dropdown-item').forEach(item => {
            item.classList.remove('active-sort');
            item.querySelector('.bi-check-lg').classList.add('d-none');
        });
        
        // Add active state to current sort
        const activeItem = document.querySelector(`.tasks-sort .dropdown-item[data-sort="${sortKey}"]`);
        if (activeItem) {
            activeItem.classList.add('active-sort');
            activeItem.querySelector('.bi-check-lg').classList.remove('d-none');
        }
    }

    function getSortFunction(sortKey) {
        switch(sortKey) {
            case sortKeys.PRIORITY:
                return (a, b) => {
                    const aCompleted = a.dataset.status === 'completed';
                    const bCompleted = b.dataset.status === 'completed';

                    // Separate completed/non-completed
                    if (aCompleted !== bCompleted) return aCompleted ? 1 : -1;

                    // Sort non-completed by priority then last modified
                    const priorityCompare = comparePriorities(a, b);
                    return priorityCompare !== 0 ? priorityCompare : compareLastModified(a, b);
                };
            
            case sortKeys.DEADLINE:
                return (a, b) => {
                    const aCompleted = a.dataset.status === 'completed';
                    const bCompleted = b.dataset.status === 'completed';

                    if (aCompleted !== bCompleted) return aCompleted ? 1 : -1;

                    const deadlineCompare = compareDeadlines(a, b);
                    return deadlineCompare !== 0 ? deadlineCompare : compareLastModified(a, b);
                };
            
            case sortKeys.LAST_MODIFIED:
                return (a, b) => {
                    const aCompleted = a.dataset.status === 'completed';
                    const bCompleted = b.dataset.status === 'completed';

                    if (aCompleted !== bCompleted) return aCompleted ? 1 : -1;

                    return compareLastModified(a, b);
                };
        }
    }

    // Comparison functions
    function comparePriorities(a, b) {
        return (priorityOrder[a.dataset.priority] || 4) - (priorityOrder[b.dataset.priority] || 4);
    }

    function compareDeadlines(a, b) {
        const aDeadline = a.dataset.deadline ? new Date(a.dataset.deadline) : Infinity;
        const bDeadline = b.dataset.deadline ? new Date(b.dataset.deadline) : Infinity;
        return aDeadline - bDeadline;
    }

    function compareLastModified(a, b) {
        return new Date(b.dataset.updated) - new Date(a.dataset.updated);
    }

    updateActiveSortUI(currentSort);
});