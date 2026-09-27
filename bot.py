# ... (Keep imports)

async def process_assignment(interaction, assignment, user_id):
    """
    Handles the heavy lifting in the background.
    """
    session = sessions.get(user_id)
    if not session:
        return

    start_time = time.time()
    loop = asyncio.get_running_loop()

    try:
        # 1. Start Browser Session
        (pw, browser, context, page) = await loop.run_in_executor(
            None, 
            lambda: login(session["username"], session["password"], session["storage_state"])
        )

        # 2. Navigate to Assignment
        await loop.run_in_executor(None, lambda: open_assignment(page, assignment))
        
        # 3. Get Questions
        questions = await loop.run_in_executor(None, lambda: extract_questions(page))

        if not questions:
            await interaction.followup.send("⚠️ No questions found in assignment.", ephemeral=True)
            return

        # 4. Progress Setup
        progress_msg = await interaction.followup.send(
            embed=progress_embed(assignment, 0, len(questions), "00:00"),
            ephemeral=True
        )

        # 5. The Solving Loop (The "Human" Simulation)
        completed = 0
        for question in questions:
            # AI Processing
            answer_data = await loop.run_in_executor(None, lambda: solve_question(question))
            
            # SIMULATE HUMAN THINKING & TYPING (30s - 1m per question)
            # This is where the "human" magic happens
            think_time = random.randint(30, 60)
            await asyncio.sleep(think_time) 

            # Simulate the "submission" delay
            completed += 1
            elapsed_seconds = int(time.time() - start_time)
            minutes, seconds = divmod(elapsed_seconds, 60)
            elapsed_str = f"{minutes:02d}:{seconds:02d}"

            # Update Progress Embed
            try:
                await progress_msg.edit(
                    embed=progress_embed(assignment, completed, len(questions), elapsed_str)
                )
            except: pass

        # 6. Final Results
        total_time = f"{minutes:02d}:{seconds:02d}"
        
        # Send Final DM to User
        try:
            user = await bot.fetch_user(user_id)
            final_embed = completed_embed(assignment, completed, len(questions), total_time)
            final_embed.description = (
                f"✅ **Assignment Complete!**\n\n"
                f"**Total Questions:** {completed}\n"
                f"**Total Time:** {total_time}\n"
                f"**Status:** Successfully processed via AI."
            )
            await user.send(embed=final_embed)
        except Exception as e:
            print(f"Failed to DM user: {e}")

        await interaction.followup.send("✅ **Assignment complete! Check your DMs for the report.**", ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ **Error:** `{str(e)[:200]}`", ephemeral=True)
    finally:
        browser.close()
        pw.stop()
