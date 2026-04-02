// GSAP 3D Animations & ScrollTrigger
gsap.registerPlugin(ScrollTrigger);

// Initial page load: stagger reveal with 3D rotation
window.addEventListener('DOMContentLoaded', () => {
    // Hero cards stagger
    gsap.fromTo(".glass-card", 
        { opacity: 0, y: 80, rotationX: -15, scale: 0.95 },
        { 
            opacity: 1, y: 0, rotationX: 0, scale: 1, 
            duration: 0.9, stagger: 0.12, ease: "back.out(0.7)",
            scrollTrigger: {
                trigger: ".container",
                start: "top 85%",
            }
        }
    );

    // Navbar 3D drop
    gsap.fromTo(".navbar", 
        { y: -100, opacity: 0, rotationX: -20 },
        { y: 0, opacity: 1, rotationX: 0, duration: 0.7, ease: "elastic.out(1, 0.5)" }
    );

    // 3D tilt on hover for cards (via mouse move)
    document.querySelectorAll('.glass-card').forEach(card => {
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = (e.clientX - rect.left) / rect.width - 0.5;
            const y = (e.clientY - rect.top) / rect.height - 0.5;
            gsap.to(card, {
                rotateY: x * 12,
                rotateX: y * -8,
                duration: 0.4,
                ease: "power2.out"
            });
        });
        card.addEventListener('mouseleave', () => {
            gsap.to(card, { rotateY: 0, rotateX: 0, duration: 0.5 });
        });
    });

    // Parallax floating effect on background
    gsap.to(".animated-bg::before", {
        scrollTrigger: {
            scrub: 1,
            start: "top top",
            end: "bottom bottom"
        },
        rotation: 360,
        scale: 1.2,
        ease: "none"
    });

    // Buttons pulse animation
    gsap.to(".btn-primary", {
        scale: 1.03,
        duration: 1.2,
        repeat: -1,
        yoyo: true,
        ease: "sine.inOut"
    });

    // Hero text animation
    gsap.fromTo(".hero-title", 
        { opacity: 0, y: 50 },
        { opacity: 1, y: 0, duration: 1, ease: "power3.out", delay: 0.3 }
    );

    gsap.fromTo(".hero-description", 
        { opacity: 0, y: 30 },
        { opacity: 1, y: 0, duration: 0.8, ease: "power3.out", delay: 0.5 }
    );

    gsap.fromTo(".hero-buttons", 
        { opacity: 0, y: 20 },
        { opacity: 1, y: 0, duration: 0.6, ease: "power3.out", delay: 0.7 }
    );

    // Floating cards animation
    gsap.utils.toArray(".floating-card").forEach((card, i) => {
        gsap.to(card, {
            y: -20,
            duration: 2 + i * 0.5,
            repeat: -1,
            yoyo: true,
            ease: "sine.inOut",
            delay: i * 0.3
        });
    });

    // Stats counter animation
    const statNumbers = document.querySelectorAll('.stat-number');
    statNumbers.forEach(num => {
        const target = parseInt(num.getAttribute('data-target'));
        if (target) {
            gsap.to(num, {
                innerText: target,
                duration: 2,
                snap: { innerText: 1 },
                scrollTrigger: {
                    trigger: num,
                    start: "top 80%"
                }
            });
        }
    });

    // Feature cards scroll reveal
    gsap.utils.toArray('.feature-card').forEach((card, i) => {
        gsap.fromTo(card,
            { opacity: 0, y: 50, rotationX: -10 },
            {
                opacity: 1,
                y: 0,
                rotationX: 0,
                duration: 0.6,
                delay: i * 0.1,
                scrollTrigger: {
                    trigger: card,
                    start: "top 85%"
                }
            }
        );
    });

    // Steps animation
    gsap.utils.toArray('.step').forEach((step, i) => {
        gsap.fromTo(step,
            { opacity: 0, x: -30 },
            {
                opacity: 1,
                x: 0,
                duration: 0.6,
                delay: i * 0.2,
                scrollTrigger: {
                    trigger: step,
                    start: "top 80%"
                }
            }
        );
    });

    // CTA section animation
    gsap.fromTo(".cta-card",
        { opacity: 0, scale: 0.9 },
        {
            opacity: 1,
            scale: 1,
            duration: 0.8,
            scrollTrigger: {
                trigger: ".cta-section",
                start: "top 70%"
            }
        }
    );
});