package com.minmessage.cli

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking

fun main(args: Array<String>) {
    if (args.isEmpty()) {
        println("Usage: minmessage <username> [ws-url]")
        return
    }

    val username = args[0]
    val wsUrl    = args.getOrElse(1) { "ws://localhost:8765" }

    val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    val client = MessagingClient { fromUser, body ->
        println("\n<- [$fromUser] $body")
        print("$username> ")
        System.out.flush()
    }

    client.initialize(username, wsUrl)
    scope.launch { client.connect() }

    // Give the connection a moment to establish before showing the prompt
    Thread.sleep(500)
    println("Connected as '$username'. Commands: @recipient message | /status | /quit")

    val reader = System.`in`.bufferedReader()
    while (true) {
        print("$username> ")
        System.out.flush()

        val line = reader.readLine() ?: break

        when {
            line == "/quit" -> {
                client.disconnect()
                break
            }
            line == "/status" -> {
                println("Status: ${client.getState()}")
            }
            line.startsWith("@") -> {
                val rest  = line.substring(1)
                val parts = rest.split(" ", limit = 2)
                if (parts.size == 2 && parts[0].isNotEmpty() && parts[1].isNotEmpty()) {
                    runBlocking { client.sendMessage(parts[0], parts[1]) }
                } else {
                    println("Usage: @recipient message text")
                }
            }
            else -> {
                println("Unknown command. Use: @recipient message | /status | /quit")
            }
        }
    }

    scope.cancel()
}
